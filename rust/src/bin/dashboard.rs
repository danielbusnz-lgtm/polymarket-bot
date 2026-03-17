/// dashboard.rs — ratatui TUI for the Polymarket bot
///
/// Layout:
///   ┌─────────────────────────┬───────────────┐
///   │  Open Signals + Kelly   │  P&L Summary  │
///   ├─────────────────────────┴───────────────┤
///   │  Equity Curve ($1,000 start)            │
///   ├─────────────────────────────────────────┤
///   │  Resolved Trades (scrollable)           │
///   └─────────────────────────────────────────┘

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
    symbols,
    text::{Line, Span},
    widgets::{Axis, Block, Borders, Cell, Chart, Dataset, GraphType, Paragraph, Row, Table, TableState},
    Terminal,
};
use rusqlite::{Connection, Result as SqlResult};

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

const STARTING_BANKROLL: f64 = 1000.0;
const MAX_KELLY_FRACTION: f64 = 0.10; // never bet more than 10% of bankroll

#[derive(Debug, Clone)]
struct Signal {
    id:        i64,
    question:  String,
    direction: String,
    price:     f64,
    edge:      f64,
    avg_prob:  f64,
    resolved:  bool,
    correct:   Option<i64>,
}

#[derive(Debug, Default)]
struct Stats {
    total:   usize,
    open:    usize,
    wins:    usize,
    losses:  usize,
}

// ---------------------------------------------------------------------------
// Kelly criterion
//
// For a prediction market bet at `price` with model probability `model_p`:
//   full Kelly  = (model_p - price) / (1 - price)
//   half Kelly  = full Kelly / 2          (standard safety divisor)
//   bet size    = half Kelly * bankroll, capped at MAX_KELLY_FRACTION
// ---------------------------------------------------------------------------
fn kelly_bet(avg_prob: f64, price: f64, direction: &str, bankroll: f64) -> f64 {
    let model_p = if direction == "YES" { avg_prob } else { 1.0 - avg_prob };
    let edge = model_p - price;
    if edge <= 0.0 || price >= 1.0 {
        return 0.0;
    }
    let full_kelly   = edge / (1.0 - price);
    let half_kelly   = full_kelly * 0.5;
    let fraction     = half_kelly.min(MAX_KELLY_FRACTION);
    fraction * bankroll
}

// ---------------------------------------------------------------------------
// DB
// ---------------------------------------------------------------------------

fn load_signals(db_path: &str) -> SqlResult<Vec<Signal>> {
    let conn = Connection::open(db_path)?;
    let mut stmt = conn.prepare(
        "SELECT id, question, direction, price, edge, avg_prob, resolved, correct
         FROM signals ORDER BY id ASC"
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(Signal {
            id:        row.get(0)?,
            question:  row.get(1)?,
            direction: row.get(2)?,
            price:     row.get(3)?,
            edge:      row.get(4)?,
            avg_prob:  row.get(5)?,
            resolved:  row.get::<_, i64>(6)? == 1,
            correct:   row.get(7)?,
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

/// Simulate bankroll growth using half-Kelly sizing on resolved trades.
/// Always returns at least 2 points so the chart renders immediately.
fn simulate_equity(signals: &[Signal]) -> Vec<(f64, f64)> {
    let mut bankroll = STARTING_BANKROLL;
    let mut points: Vec<(f64, f64)> = vec![(0.0, bankroll)];

    let resolved: Vec<&Signal> = signals.iter().filter(|s| s.resolved).collect();

    for (i, s) in resolved.iter().enumerate() {
        let bet = kelly_bet(s.avg_prob, s.price, &s.direction, bankroll);
        match s.correct {
            Some(1) => {
                // WIN: profit = bet * (1 - price) / price  (shares pay $1, cost price each)
                let profit = bet * (1.0 - s.price) / s.price;
                bankroll += profit;
            }
            Some(0) => {
                // LOSS: lose the bet
                bankroll -= bet;
            }
            _ => {}
        }
        bankroll = bankroll.max(0.0);
        points.push(((i + 1) as f64, bankroll));
    }

    // Always pad to at least 2 points so the chart renders even with no resolved trades
    if points.len() == 1 {
        points.push((1.0, STARTING_BANKROLL));
    }

    points
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

struct App {
    db_path:       String,
    signals:       Vec<Signal>,
    stats:         Stats,
    equity:        Vec<(f64, f64)>,
    table_state:   TableState,
    last_refresh:  Instant,
    scroll_offset: usize,
}

impl App {
    fn new(db_path: &str) -> Self {
        let mut app = Self {
            db_path:       db_path.to_string(),
            signals:       vec![],
            stats:         Stats::default(),
            equity:        vec![(0.0, STARTING_BANKROLL)],
            table_state:   TableState::default(),
            last_refresh:  Instant::now(),
            scroll_offset: 0,
        };
        app.refresh();
        app
    }

    fn refresh(&mut self) {
        if let Ok(signals) = load_signals(&self.db_path) {
            self.stats   = calc_stats(&signals);
            self.equity  = simulate_equity(&signals);
            self.signals = signals;
        }
        self.last_refresh = Instant::now();
    }

    fn scroll_down(&mut self) {
        let resolved = self.signals.iter().filter(|s| s.resolved).count();
        if self.scroll_offset + 1 < resolved {
            self.scroll_offset += 1;
        }
    }

    fn scroll_up(&mut self) {
        self.scroll_offset = self.scroll_offset.saturating_sub(1);
    }
}

// ---------------------------------------------------------------------------
// UI
// ---------------------------------------------------------------------------

fn ui(frame: &mut ratatui::Frame, app: &mut App) {
    let area = frame.area();

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage(30),
            Constraint::Percentage(30),
            Constraint::Percentage(40),
        ])
        .split(area);

    // Top row: signals + P&L side by side
    let top = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(65), Constraint::Percentage(35)])
        .split(rows[0]);

    render_open_signals(frame, app, top[0]);
    render_pnl(frame, app, top[1]);
    render_equity_chart(frame, app, rows[1]);
    render_history(frame, app, rows[2]);
}

fn render_open_signals(frame: &mut ratatui::Frame, app: &App, area: ratatui::layout::Rect) {
    let open: Vec<&Signal> = app.signals.iter().filter(|s| !s.resolved).collect();

    // Use current bankroll (last point in equity curve) for Kelly sizing
    let bankroll = app.equity.last().map(|p| p.1).unwrap_or(STARTING_BANKROLL);

    let header = Row::new(vec!["#", "Dir", "Edge", "Kelly $", "Question"])
        .style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));

    let rows: Vec<Row> = open.iter().map(|s| {
        let q = if s.question.len() > 34 {
            format!("{}…", &s.question[..33])
        } else {
            s.question.clone()
        };

        let bet     = kelly_bet(s.avg_prob, s.price, &s.direction, bankroll);
        let edge_color = if s.edge >= 0.20 { Color::Green }
                         else if s.edge >= 0.12 { Color::Cyan }
                         else { Color::White };

        Row::new(vec![
            Cell::from(s.id.to_string()),
            Cell::from(s.direction.clone()).style(Style::default().fg(
                if s.direction == "YES" { Color::Green } else { Color::Red }
            )),
            Cell::from(format!("{:.0}%", s.edge * 100.0))
                .style(Style::default().fg(edge_color)),
            Cell::from(format!("${:.0}", bet))
                .style(Style::default().fg(Color::Magenta)),
            Cell::from(q),
        ])
    }).collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Length(5),
            Constraint::Length(8),
            Constraint::Min(10),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(" Open Signals ({}) — half-Kelly sizing ", open.len()))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );

    frame.render_widget(table, area);
}

fn render_pnl(frame: &mut ratatui::Frame, app: &App, area: ratatui::layout::Rect) {
    let resolved  = app.stats.wins + app.stats.losses;
    let win_rate  = if resolved > 0 {
        format!("{:.1}%", app.stats.wins as f64 / resolved as f64 * 100.0)
    } else {
        "—".to_string()
    };
    let bankroll  = app.equity.last().map(|p| p.1).unwrap_or(STARTING_BANKROLL);
    let pnl       = bankroll - STARTING_BANKROLL;
    let pnl_color = if pnl >= 0.0 { Color::Green } else { Color::Red };
    let wr_color  = if resolved == 0 { Color::White }
                    else if app.stats.wins as f64 / resolved.max(1) as f64 >= 0.60 { Color::Green }
                    else { Color::Red };

    let secs = app.last_refresh.elapsed().as_secs();

    let text = vec![
        Line::from(""),
        Line::from(vec![
            Span::raw("  Bankroll : "),
            Span::styled(
                format!("${bankroll:.0}"),
                Style::default().fg(pnl_color).add_modifier(Modifier::BOLD),
            ),
        ]),
        Line::from(vec![
            Span::raw("  P&L      : "),
            Span::styled(
                format!("{}{:.0}", if pnl >= 0.0 { "+" } else { "" }, pnl),
                Style::default().fg(pnl_color),
            ),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::raw("  Signals  : "),
            Span::styled(app.stats.total.to_string(), Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::raw("  Open     : "),
            Span::styled(app.stats.open.to_string(), Style::default().fg(Color::Cyan)),
        ]),
        Line::from(vec![
            Span::raw("  Wins     : "),
            Span::styled(app.stats.wins.to_string(), Style::default().fg(Color::Green)),
        ]),
        Line::from(vec![
            Span::raw("  Losses   : "),
            Span::styled(app.stats.losses.to_string(), Style::default().fg(Color::Red)),
        ]),
        Line::from(vec![
            Span::raw("  Win rate : "),
            Span::styled(win_rate, Style::default().fg(wr_color).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(""),
        Line::from(Span::styled(
            format!("  [{secs}s ago] r=refresh q=quit"),
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

fn render_equity_chart(frame: &mut ratatui::Frame, app: &App, area: ratatui::layout::Rect) {
    let data = &app.equity;

    let max_x = data.last().map(|p| p.0).unwrap_or(1.0).max(1.0);
    let min_y = data.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
    let max_y = data.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);

    // Pad Y range so the line doesn't hug the edges
    let y_pad   = ((max_y - min_y) * 0.15).max(50.0);
    let y_min   = (min_y - y_pad).max(0.0);
    let y_max   = max_y + y_pad;

    // Color: green if profitable, red if below starting bankroll
    let current  = data.last().map(|p| p.1).unwrap_or(STARTING_BANKROLL);
    let line_color = if current >= STARTING_BANKROLL { Color::Green } else { Color::Red };

    let dataset = Dataset::default()
        .name("Bankroll")
        .marker(symbols::Marker::Braille)
        .graph_type(GraphType::Line)
        .style(Style::default().fg(line_color))
        .data(data);

    // X axis labels
    let x_labels = vec![
        ratatui::text::Span::raw("0"),
        ratatui::text::Span::raw(format!("{}", (max_x / 2.0).round() as usize)),
        ratatui::text::Span::raw(format!("{}", max_x as usize)),
    ];

    // Y axis labels
    let y_labels = vec![
        ratatui::text::Span::raw(format!("${:.0}", y_min)),
        ratatui::text::Span::raw(format!("${:.0}", (y_min + y_max) / 2.0)),
        ratatui::text::Span::raw(format!("${:.0}", y_max)),
    ];

    let chart = Chart::new(vec![dataset])
        .block(
            Block::default()
                .title(format!(
                    " Equity Curve — ${:.0} simulated bankroll (half-Kelly) ",
                    current
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::Cyan)),
        )
        .x_axis(
            Axis::default()
                .title("Trades")
                .style(Style::default().fg(Color::DarkGray))
                .bounds([0.0, max_x])
                .labels(x_labels),
        )
        .y_axis(
            Axis::default()
                .title("Bankroll ($)")
                .style(Style::default().fg(Color::DarkGray))
                .bounds([y_min, y_max])
                .labels(y_labels),
        );

    frame.render_widget(chart, area);
}

fn render_history(frame: &mut ratatui::Frame, app: &mut App, area: ratatui::layout::Rect) {
    let resolved: Vec<&Signal> = app.signals.iter().filter(|s| s.resolved).collect();

    let bankroll    = STARTING_BANKROLL;
    let visible     = (area.height as usize).saturating_sub(3);
    let start       = app.scroll_offset.min(resolved.len().saturating_sub(visible));

    let header = Row::new(vec!["#", "Dir", "Edge", "Kelly $", "Result", "Question"])
        .style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));

    let rows: Vec<Row> = resolved.iter().skip(start).take(visible).map(|s| {
        let q = if s.question.len() > 34 {
            format!("{}…", &s.question[..33])
        } else {
            s.question.clone()
        };
        let bet = kelly_bet(s.avg_prob, s.price, &s.direction, bankroll);
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
            Cell::from(format!("{:.0}%", s.edge * 100.0)),
            Cell::from(format!("${:.0}", bet))
                .style(Style::default().fg(Color::Magenta)),
            Cell::from(result_str).style(Style::default().fg(result_color).add_modifier(Modifier::BOLD)),
            Cell::from(q),
        ])
    }).collect();

    let table = Table::new(
        rows,
        [
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Length(5),
            Constraint::Length(8),
            Constraint::Length(5),
            Constraint::Min(10),
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(format!(" Resolved Trades ({}) ", resolved.len()))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan)),
    );

    frame.render_stateful_widget(table, area, &mut app.table_state);
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

fn main() -> io::Result<()> {
    let db_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "python/paper_trades.db".to_string());

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;

    let backend      = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    let mut app      = App::new(&db_path);

    loop {
        terminal.draw(|f| ui(f, &mut app))?;

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

        if app.last_refresh.elapsed() >= Duration::from_secs(2) {
            app.refresh();
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, DisableMouseCapture)?;
    terminal.show_cursor()?;
    Ok(())
}
