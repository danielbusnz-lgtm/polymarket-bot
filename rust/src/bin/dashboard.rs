/// dashboard.rs — ratatui TUI for the Polymarket bot
///
/// Reads paper_trades.db and refreshes every 30 seconds.
/// Layout:
///   ┌─────────────────────┬───────────────┐
///   │  Open Signals       │  P&L Summary  │
///   ├─────────────────────┴───────────────┤
///   │  Resolved Trades (scrollable)       │
///   └─────────────────────────────────────┘

use std::{
    io,
    time::{Duration, Instant},
};

use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Cell, Paragraph, Row, Table, TableState},
    Terminal,
};
use rusqlite::{Connection, Result as SqlResult};

// ---------------------------------------------------------------------------
// Data structs
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct Signal {
    id:          i64,
    run_at:      String,
    question:    String,
    direction:   String,
    price:       f64,
    edge:        f64,
    resolved:    bool,
    outcome:     Option<String>,
    correct:     Option<i64>,
}

#[derive(Debug, Default)]
struct Stats {
    total:    usize,
    open:     usize,
    wins:     usize,
    losses:   usize,
}

// ---------------------------------------------------------------------------
// DB helpers
// ---------------------------------------------------------------------------

fn load_signals(db_path: &str) -> SqlResult<Vec<Signal>> {
    let conn = Connection::open(db_path)?;
    let mut stmt = conn.prepare(
        "SELECT id, run_at, question, direction, price, edge, resolved, outcome, correct
         FROM signals ORDER BY id DESC LIMIT 100"
    )?;

    let rows = stmt.query_map([], |row| {
        Ok(Signal {
            id:        row.get(0)?,
            run_at:    row.get(1)?,
            question:  row.get(2)?,
            direction: row.get(3)?,
            price:     row.get(4)?,
            edge:      row.get(5)?,
            resolved:  row.get::<_, i64>(6)? == 1,
            outcome:   row.get(7)?,
            correct:   row.get(8)?,
        })
    })?;

    rows.collect()
}

fn calc_stats(signals: &[Signal]) -> Stats {
    Stats {
        total:   signals.len(),
        open:    signals.iter().filter(|s| !s.resolved).count(),
        wins:    signals.iter().filter(|s| s.correct == Some(1)).count(),
        losses:  signals.iter().filter(|s| s.correct == Some(0)).count(),
    }
}

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------

struct App {
    db_path:      String,
    signals:      Vec<Signal>,
    stats:        Stats,
    table_state:  TableState,
    last_refresh: Instant,
    scroll_offset: usize,
}

impl App {
    fn new(db_path: &str) -> Self {
        let mut app = Self {
            db_path:      db_path.to_string(),
            signals:      vec![],
            stats:        Stats::default(),
            table_state:  TableState::default(),
            last_refresh: Instant::now(),
            scroll_offset: 0,
        };
        app.refresh();
        app
    }

    fn refresh(&mut self) {
        if let Ok(signals) = load_signals(&self.db_path) {
            self.stats   = calc_stats(&signals);
            self.signals = signals;
        }
        self.last_refresh = Instant::now();
    }

    fn scroll_down(&mut self) {
        if self.scroll_offset + 1 < self.signals.len() {
            self.scroll_offset += 1;
        }
    }

    fn scroll_up(&mut self) {
        self.scroll_offset = self.scroll_offset.saturating_sub(1);
    }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

fn ui(frame: &mut ratatui::Frame, app: &mut App) {
    let area = frame.area();

    // Split top/bottom
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(40), Constraint::Percentage(60)])
        .split(area);

    // Split top into left (open signals) and right (P&L)
    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(65), Constraint::Percentage(35)])
        .split(vertical[0]);

    render_open_signals(frame, app, top[0]);
    render_pnl(frame, app, top[1]);
    render_history(frame, app, vertical[1]);
}

fn render_open_signals(frame: &mut ratatui::Frame, app: &App, area: ratatui::layout::Rect) {
    let open: Vec<&Signal> = app.signals.iter().filter(|s| !s.resolved).collect();

    let header = Row::new(vec!["#", "Dir", "Price", "Edge", "Question"])
        .style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));

    let rows: Vec<Row> = open.iter().map(|s| {
        let q = if s.question.len() > 38 {
            format!("{}…", &s.question[..37])
        } else {
            s.question.clone()
        };
        let edge_color = if s.edge >= 0.20 { Color::Green }
                         else if s.edge >= 0.12 { Color::Cyan }
                         else { Color::White };
        Row::new(vec![
            Cell::from(s.id.to_string()),
            Cell::from(s.direction.clone()).style(Style::default().fg(
                if s.direction == "YES" { Color::Green } else { Color::Red }
            )),
            Cell::from(format!("{:.2}", s.price)),
            Cell::from(format!("{:.0}%", s.edge * 100.0))
                .style(Style::default().fg(edge_color)),
            Cell::from(q),
        ])
    }).collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Length(6),
            Constraint::Length(5),
            Constraint::Min(10),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(" Open Signals ({}) ", open.len()))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );

    frame.render_widget(table, area);
}

fn render_pnl(frame: &mut ratatui::Frame, app: &App, area: ratatui::layout::Rect) {
    let resolved = app.stats.wins + app.stats.losses;
    let win_rate = if resolved > 0 {
        format!("{:.1}%", app.stats.wins as f64 / resolved as f64 * 100.0)
    } else {
        "—".to_string()
    };

    let wr_color = if resolved == 0 { Color::White }
                   else if app.stats.wins as f64 / resolved.max(1) as f64 >= 0.60 { Color::Green }
                   else { Color::Red };

    let secs = app.last_refresh.elapsed().as_secs();

    let text = vec![
        Line::from(""),
        Line::from(vec![
            Span::raw("  Total signals : "),
            Span::styled(app.stats.total.to_string(), Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::raw("  Open          : "),
            Span::styled(app.stats.open.to_string(), Style::default().fg(Color::Cyan)),
        ]),
        Line::from(vec![
            Span::raw("  Resolved      : "),
            Span::styled(resolved.to_string(), Style::default().fg(Color::White)),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::raw("  Wins          : "),
            Span::styled(app.stats.wins.to_string(), Style::default().fg(Color::Green)),
        ]),
        Line::from(vec![
            Span::raw("  Losses        : "),
            Span::styled(app.stats.losses.to_string(), Style::default().fg(Color::Red)),
        ]),
        Line::from(vec![
            Span::raw("  Win rate      : "),
            Span::styled(win_rate, Style::default().fg(wr_color).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::raw("  Refreshed     : "),
            Span::styled(format!("{secs}s ago"), Style::default().fg(Color::DarkGray)),
        ]),
        Line::from(""),
        Line::from(Span::styled(
            "  [↑↓] scroll  [r] refresh  [q] quit",
            Style::default().fg(Color::DarkGray),
        )),
    ];

    let para = Paragraph::new(text).block(
        Block::default()
            .title(" P&L Summary ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );

    frame.render_widget(para, area);
}

fn render_history(frame: &mut ratatui::Frame, app: &mut App, area: ratatui::layout::Rect) {
    let resolved: Vec<&Signal> = app.signals.iter().filter(|s| s.resolved).collect();

    let header = Row::new(vec!["#", "Dir", "Price", "Edge", "Result", "Question"])
        .style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));

    let visible_rows = (area.height as usize).saturating_sub(3); // minus border + header
    let start = app.scroll_offset.min(resolved.len().saturating_sub(visible_rows));

    let rows: Vec<Row> = resolved.iter().skip(start).take(visible_rows).map(|s| {
        let q = if s.question.len() > 38 {
            format!("{}…", &s.question[..37])
        } else {
            s.question.clone()
        };
        let (result_str, result_color) = match s.correct {
            Some(1) => ("WIN",  Color::Green),
            Some(0) => ("LOSS", Color::Red),
            _       => ("?",    Color::White),
        };
        Row::new(vec![
            Cell::from(s.id.to_string()),
            Cell::from(s.direction.clone()).style(Style::default().fg(
                if s.direction == "YES" { Color::Green } else { Color::Red }
            )),
            Cell::from(format!("{:.2}", s.price)),
            Cell::from(format!("{:.0}%", s.edge * 100.0)),
            Cell::from(result_str).style(Style::default().fg(result_color).add_modifier(Modifier::BOLD)),
            Cell::from(q),
        ])
    }).collect();

    let title = format!(" Resolved Trades ({}) — ↑↓ to scroll ", resolved.len());

    let table = Table::new(
        rows,
        [
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Length(6),
            Constraint::Length(5),
            Constraint::Length(5),
            Constraint::Min(10),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(title)
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );

    frame.render_stateful_widget(table, area, &mut app.table_state);
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

fn main() -> io::Result<()> {
    // Find the SQLite DB — look relative to where the binary is run from
    let db_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "python/paper_trades.db".to_string());

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;

    let backend  = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut app = App::new(&db_path);
    let refresh_interval = Duration::from_secs(30);

    loop {
        terminal.draw(|f| ui(f, &mut app))?;

        // Poll for key events with a short timeout so we can auto-refresh
        if event::poll(Duration::from_millis(250))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') | KeyCode::Char('Q') => break,
                    KeyCode::Char('r') | KeyCode::Char('R') => app.refresh(),
                    KeyCode::Down  | KeyCode::Char('j') => app.scroll_down(),
                    KeyCode::Up    | KeyCode::Char('k') => app.scroll_up(),
                    _ => {}
                }
            }
        }

        // Auto-refresh every 30 seconds
        if app.last_refresh.elapsed() >= refresh_interval {
            app.refresh();
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    Ok(())
}
