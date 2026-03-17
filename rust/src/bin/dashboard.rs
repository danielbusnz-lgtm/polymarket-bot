use rusqlite::{Connection, Result as SqlResult, params};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    symbols,
    text::{Line, Span},
    widgets::{Axis, Block, Borders, Cell, Chart, Dataset, GraphType, Row, Table, Tabs},
    Terminal,
};
use crossterm::{
    event::{self, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use std::io;

const DB_PATH: &str = "bot.db";
const SNAPSHOT_INTERVAL_SECS: u64 = 15 * 60; // 15 minutes
const CRON_INTERVAL_SECS: u64    = 6 * 60 * 60; // 6 hours

// ---------------------------------------------------------------------------
// Data structs
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct PortfolioSnapshot {
    timestamp: i64,
    value:     f64,
}

#[derive(Debug, Clone)]
struct Position {
    title:         String,
    direction:     String,  // "YES" or "NO"
    amount_in:     f64,     // how much we invested
    current_value: f64,     // what it's worth now
    our_prob:      f64,     // our model's probability
    market_prob:   f64,     // current market price
    opened_at:     i64,
}

// ---------------------------------------------------------------------------
// DB init
// ---------------------------------------------------------------------------

fn init_db(conn: &Connection) -> SqlResult<()> {
    conn.execute_batch("
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id        INTEGER PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            value     REAL NOT NULL,
            is_paper  INTEGER NOT NULL  -- 0 = live, 1 = paper
        );

        CREATE TABLE IF NOT EXISTS positions (
            id            INTEGER PRIMARY KEY,
            title         TEXT NOT NULL,
            direction     TEXT NOT NULL,   -- YES or NO
            amount_in     REAL NOT NULL,   -- how much we invested
            current_value REAL NOT NULL,   -- what it's worth now
            our_prob      REAL NOT NULL,   -- our model's probability
            market_prob   REAL NOT NULL,   -- current market price
            is_paper      INTEGER NOT NULL, -- 0 = live, 1 = paper
            opened_at     INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cron_runs (
            id     INTEGER PRIMARY KEY,
            ran_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS signals (
            id            INTEGER PRIMARY KEY,
            run_at        TEXT    NOT NULL,
            market_id     TEXT    NOT NULL,
            question      TEXT    NOT NULL,
            direction     TEXT    NOT NULL,
            price         REAL    NOT NULL,  -- market price at signal time
            edge          REAL    NOT NULL,  -- our edge (our_prob - market_price)
            avg_prob      REAL    NOT NULL,  -- our model's probability
            disagreement  REAL    NOT NULL,
            resolved      INTEGER NOT NULL DEFAULT 0,
            outcome       TEXT,              -- nullable until resolved
            correct       INTEGER,           -- nullable until resolved
            token_id      TEXT    NOT NULL DEFAULT ''
        );
    ")
}

// ---------------------------------------------------------------------------
// DB query functions
// ---------------------------------------------------------------------------

/// Load portfolio snapshots for one tab (live or paper), ordered by time.
fn load_snapshots(conn: &Connection, is_paper: bool) -> SqlResult<Vec<PortfolioSnapshot>> {
    let flag = if is_paper { 1 } else { 0 };
    let mut stmt = conn.prepare(
        "SELECT timestamp, value FROM portfolio_snapshots
         WHERE is_paper = ?1
         ORDER BY timestamp ASC"
    )?;
    let rows = stmt.query_map(params![flag], |row| {
        Ok(PortfolioSnapshot {
            timestamp: row.get(0)?,
            value:     row.get(1)?,
        })
    })?;
    rows.collect()
}

/// Load open positions for one tab (live or paper).
fn load_positions(conn: &Connection, is_paper: bool) -> SqlResult<Vec<Position>> {
    let flag = if is_paper { 1 } else { 0 };
    let mut stmt = conn.prepare(
        "SELECT title, direction, amount_in, current_value,
                our_prob, market_prob, opened_at
         FROM positions
         WHERE is_paper = ?1
         ORDER BY opened_at DESC"
    )?;
    let rows = stmt.query_map(params![flag], |row| {
        Ok(Position {
            title:         row.get(0)?,
            direction:     row.get(1)?,
            amount_in:     row.get(2)?,
            current_value: row.get(3)?,
            our_prob:      row.get(4)?,
            market_prob:   row.get(5)?,
            opened_at:     row.get(6)?,
        })
    })?;
    rows.collect()
}

/// Return the Unix timestamp of the most recent cron run, or None if no runs yet.
fn last_cron_run(conn: &Connection) -> SqlResult<Option<i64>> {
    let result = conn.query_row(
        "SELECT ran_at FROM cron_runs ORDER BY ran_at DESC LIMIT 1",
        [],
        |row| row.get::<_, i64>(0),
    );
    match result {
        Ok(ts)                                      => Ok(Some(ts)),
        Err(rusqlite::Error::QueryReturnedNoRows)   => Ok(None),
        Err(e)                                      => Err(e),
    }
}

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------

struct App {
    active_tab:      usize,
    live_snapshots:  Vec<PortfolioSnapshot>,
    live_positions:  Vec<Position>,
    paper_snapshots: Vec<PortfolioSnapshot>,
    paper_positions: Vec<Position>,
    demo_snapshots:  Vec<PortfolioSnapshot>,
    demo_positions:  Vec<Position>,
    last_cron:       Option<i64>,
}

impl App {
    fn load(conn: &Connection) -> anyhow::Result<Self> {
        Ok(Self {
            active_tab:      0,
            live_snapshots:  load_snapshots(conn, false)?,
            live_positions:  load_positions(conn, false)?,
            paper_snapshots: load_snapshots(conn, true)?,
            paper_positions: load_positions(conn, true)?,
            demo_snapshots:  demo_snapshots(),
            demo_positions:  demo_positions(),
            last_cron:       last_cron_run(conn)?,
        })
    }

    fn refresh(&mut self, conn: &Connection) -> anyhow::Result<()> {
        self.live_snapshots  = load_snapshots(conn, false)?;
        self.live_positions  = load_positions(conn, false)?;
        self.paper_snapshots = load_snapshots(conn, true)?;
        self.paper_positions = load_positions(conn, true)?;
        self.last_cron       = last_cron_run(conn)?;
        Ok(())
    }

    /// Seconds until the next cron run (based on last run + 6h interval).
    /// Returns None if no cron run has happened yet.
    fn secs_until_next_cron(&self) -> Option<i64> {
        let last = self.last_cron?;
        let next = last + CRON_INTERVAL_SECS as i64;
        let now  = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        Some((next - now).max(0))
    }

    fn snapshots(&self) -> &[PortfolioSnapshot] {
        match self.active_tab {
            0 => &self.live_snapshots,
            1 => &self.paper_snapshots,
            _ => &self.demo_snapshots,
        }
    }

    fn positions(&self) -> &[Position] {
        match self.active_tab {
            0 => &self.live_positions,
            1 => &self.paper_positions,
            _ => &self.demo_positions,
        }
    }
}

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------

fn demo_snapshots() -> Vec<PortfolioSnapshot> {
    let base_values = [
        1000.0, 1012.0, 998.0, 1025.0, 1040.0, 1035.0, 1060.0, 1055.0,
        1080.0, 1072.0, 1095.0, 1110.0, 1098.0, 1125.0, 1140.0, 1132.0,
        1158.0, 1170.0, 1162.0, 1185.0, 1200.0, 1192.0, 1215.0, 1230.0,
    ];
    base_values.iter().enumerate()
        .map(|(i, &v)| PortfolioSnapshot { timestamp: i as i64, value: v })
        .collect()
}

fn demo_positions() -> Vec<Position> {
    vec![
        Position {
            title:         "Will Trump sign an executive order on crypto before April 2025?".to_string(),
            direction:     "YES".to_string(),
            amount_in:     50.0,
            current_value: 68.50,
            our_prob:      0.82,
            market_prob:   0.74,
            opened_at:     0,
        },
        Position {
            title:         "Will the Fed cut rates in March 2025?".to_string(),
            direction:     "NO".to_string(),
            amount_in:     30.0,
            current_value: 24.90,
            our_prob:      0.35,
            market_prob:   0.41,
            opened_at:     0,
        },
        Position {
            title:         "Will Bitcoin hit $100k before June 2025?".to_string(),
            direction:     "YES".to_string(),
            amount_in:     75.0,
            current_value: 91.25,
            our_prob:      0.68,
            market_prob:   0.55,
            opened_at:     0,
        },
        Position {
            title:         "Will Nvidia stock close above $1000 in Q1 2025?".to_string(),
            direction:     "NO".to_string(),
            amount_in:     20.0,
            current_value: 16.40,
            our_prob:      0.28,
            market_prob:   0.33,
            opened_at:     0,
        },
    ]
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

fn draw(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, app: &App) -> anyhow::Result<()> {
    terminal.draw(|frame| {
        let area = frame.area();

        // Split into: tab bar | body | status bar
        let root = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(3),   // tab bar
                Constraint::Min(0),      // body
                Constraint::Length(1),   // status bar
            ])
            .split(area);

        // --- Tab bar ---
        let tab_titles = vec![
            Line::from(Span::raw(" Live ")),
            Line::from(Span::raw(" Paper ")),
            Line::from(Span::raw(" Demo ")),
        ];
        let tabs = Tabs::new(tab_titles)
            .select(app.active_tab)
            .block(Block::default().borders(Borders::ALL).title("Polymarket Bot"))
            .highlight_style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD))
            .divider("|");
        frame.render_widget(tabs, root[0]);

        // Split body into: chart (top 40%) | table (bottom 60%)
        let body = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Percentage(40),
                Constraint::Percentage(60),
            ])
            .split(root[1]);

        // --- Portfolio chart ---
        let snapshots = app.snapshots();
        let chart_data: Vec<(f64, f64)> = snapshots.iter().enumerate()
            .map(|(i, s)| (i as f64, s.value))
            .collect();

        let (min_val, max_val) = if chart_data.is_empty() {
            (0.0, 1.0)
        } else {
            let min = chart_data.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
            let max = chart_data.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
            let padding = (max - min) * 0.1;
            (min - padding, max + padding)
        };

        let dataset = Dataset::default()
            .marker(symbols::Marker::Braille)
            .graph_type(GraphType::Line)
            .style(Style::default().fg(Color::Cyan))
            .data(&chart_data);

        let current_value = snapshots.last().map(|s| s.value).unwrap_or(0.0);
        let chart_title = format!("Portfolio Value  ${:.2}", current_value);

        let chart = Chart::new(vec![dataset])
            .block(Block::default().borders(Borders::ALL).title(chart_title))
            .x_axis(Axis::default().bounds([0.0, chart_data.len().max(1) as f64]))
            .y_axis(
                Axis::default()
                    .bounds([min_val, max_val])
                    .labels(vec![
                        Span::raw(format!("${:.0}", min_val)),
                        Span::raw(format!("${:.0}", max_val)),
                    ]),
            );
        frame.render_widget(chart, body[0]);

        // --- Positions table ---
        let header = Row::new(vec!["Market", "Dir", "In", "Value", "P&L", "Our%", "Mkt%"])
            .style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD))
            .height(1);

        let rows: Vec<Row> = app.positions().iter().map(|p| {
            let pnl     = p.current_value - p.amount_in;
            let pnl_color = if pnl >= 0.0 { Color::Green } else { Color::Red };
            let dir_color = if p.direction == "YES" { Color::Green } else { Color::Red };

            // Truncate long market titles to fit the column
            let title = if p.title.len() > 35 {
                format!("{}...", &p.title[..32])
            } else {
                p.title.clone()
            };

            Row::new(vec![
                Cell::from(title),
                Cell::from(p.direction.clone()).style(Style::default().fg(dir_color)),
                Cell::from(format!("${:.2}", p.amount_in)),
                Cell::from(format!("${:.2}", p.current_value)),
                Cell::from(format!("{:+.2}", pnl)).style(Style::default().fg(pnl_color)),
                Cell::from(format!("{:.0}%", p.our_prob * 100.0)),
                Cell::from(format!("{:.0}%", p.market_prob * 100.0)),
            ])
        }).collect();

        let table = Table::new(
            rows,
            [
                Constraint::Min(36),      // Market title
                Constraint::Length(4),    // Dir
                Constraint::Length(8),    // In
                Constraint::Length(8),    // Value
                Constraint::Length(8),    // P&L
                Constraint::Length(6),    // Our%
                Constraint::Length(6),    // Mkt%
            ],
        )
        .header(header)
        .block(Block::default().borders(Borders::ALL).title("Open Positions"));
        frame.render_widget(table, body[1]);

        // --- Status bar ---
        let cron_text = match app.secs_until_next_cron() {
            None     => "Next LLM run: pending first run".to_string(),
            Some(s)  => format!("Next LLM run in: {}h {}m", s / 3600, (s % 3600) / 60),
        };
        let status = Line::from(vec![
            Span::styled(cron_text, Style::default().fg(Color::DarkGray)),
            Span::raw("   "),
            Span::styled("q", Style::default().fg(Color::Yellow)),
            Span::styled(" quit  ", Style::default().fg(Color::DarkGray)),
            Span::styled("Tab", Style::default().fg(Color::Yellow)),
            Span::styled(" switch tab", Style::default().fg(Color::DarkGray)),
        ]);
        frame.render_widget(status, root[2]);
    })?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

fn main() -> anyhow::Result<()> {
    let conn = Connection::open(DB_PATH)?;
    init_db(&conn)?;

    // Set up terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend  = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut app           = App::load(&conn)?;
    let mut last_refresh  = std::time::Instant::now();
    let refresh_interval  = std::time::Duration::from_secs(30);

    loop {
        draw(&mut terminal, &app)?;

        // Poll for a key event with a 250ms timeout so the loop stays responsive
        if event::poll(std::time::Duration::from_millis(250))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') | KeyCode::Char('Q') => break,
                    KeyCode::Tab => {
                        app.active_tab = (app.active_tab + 1) % 3;
                    }
                    _ => {}
                }
            }
        }

        // Refresh data from DB every 30 seconds
        if last_refresh.elapsed() >= refresh_interval {
            app.refresh(&conn)?;
            last_refresh = std::time::Instant::now();
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    Ok(())
}
