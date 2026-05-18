"""SQLite ledger schema for paper trading.

Holds the full audit trail of what we've seen, what Claude predicted, what
orders we placed, what filled, and the equity curve over time. Single-writer
SQLite is fine for a personal bot — no concurrency concerns.

Run `python ledger.py` to initialize (or re-verify) the schema. Existing
tables are untouched.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "signum.db"


SCHEMA = """
-- Markets we've ever seen. One row per distinct Polymarket market.
CREATE TABLE IF NOT EXISTS markets (
    id              TEXT PRIMARY KEY,           -- gamma id
    condition_id    TEXT UNIQUE NOT NULL,        -- on-chain identifier
    question        TEXT NOT NULL,
    slug            TEXT NOT NULL,
    end_date        TEXT,                        -- ISO 8601
    outcomes        TEXT NOT NULL,               -- JSON: ["Yes","No"]
    neg_risk        INTEGER NOT NULL,            -- 0/1
    first_seen_at   TEXT NOT NULL,               -- ISO 8601
    resolved_at     TEXT,                        -- null until resolved
    winning_outcome TEXT                         -- null until resolved
);

-- Polymarket state snapshot per cycle. The data we used to make decisions
-- AND the data we use to mark open paper positions to market.
CREATE TABLE IF NOT EXISTS market_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id         TEXT NOT NULL REFERENCES markets(id),
    snapshot_at       TEXT NOT NULL,             -- ISO 8601
    outcome_prices    TEXT NOT NULL,             -- JSON: [0.0135, 0.9865]
    volume_24hr       REAL,
    liquidity         REAL,
    accepting_orders  INTEGER NOT NULL           -- 0/1
);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_market_at
    ON market_snapshots(market_id, snapshot_at);

-- Claude's probability estimate per market per cycle. Links to the
-- market_snapshot it was made on so we can replay decisions later.
-- Cost columns track API spend so we can compute net P&L (trade gains
-- minus AI cost). Each call records its own token + search usage.
CREATE TABLE IF NOT EXISTS predictions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id          TEXT NOT NULL REFERENCES markets(id),
    snapshot_id        INTEGER REFERENCES market_snapshots(id),
    predicted_at       TEXT NOT NULL,
    model              TEXT NOT NULL,            -- e.g. 'claude-opus-4-7'
    prompt_version     TEXT NOT NULL,            -- 'v1', 'v2', ...
    yes_probability    REAL NOT NULL,            -- in [0, 1]
    confidence         TEXT,                     -- 'HIGH','MEDIUM','LOW','UNKNOWN'
    raw_response       TEXT,                     -- full claude text for debugging
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    cache_read_tokens  INTEGER,
    cache_write_tokens INTEGER,
    web_searches       INTEGER,
    cost_usd           REAL                      -- computed from tokens + pricing
);
CREATE INDEX IF NOT EXISTS idx_predictions_market_at
    ON predictions(market_id, predicted_at);

-- Paper orders we "placed". An order may have 0 or more fills (usually 1).
CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id      TEXT NOT NULL REFERENCES markets(id),
    prediction_id  INTEGER REFERENCES predictions(id),
    outcome_index  INTEGER NOT NULL,             -- 0=Yes, 1=No (or higher for neg_risk)
    side           TEXT NOT NULL,                -- 'buy' or 'sell'
    size           REAL NOT NULL,                -- shares
    limit_price    REAL NOT NULL,
    placed_at      TEXT NOT NULL,
    status         TEXT NOT NULL,                -- 'open','filled','cancelled','resolved'
    reason         TEXT                          -- human note
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_market ON orders(market_id);

-- When a paper order "fills" against real market data. Conservative model:
-- a buy at limit L fills if real market ask <= L at the snapshot moment.
CREATE TABLE IF NOT EXISTS fills (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id  INTEGER NOT NULL REFERENCES orders(id),
    filled_at TEXT NOT NULL,
    price     REAL NOT NULL,                     -- limit price (conservative)
    size      REAL NOT NULL                      -- usually = order.size
);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);

-- The "P&L over time" series. One row per cycle.
-- total_equity = cash + open_positions_value (realized P&L is already in cash).
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at              TEXT NOT NULL,
    cash                     REAL NOT NULL,
    open_positions_value     REAL NOT NULL,
    realized_pnl_cumulative  REAL NOT NULL,
    total_equity             REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_at ON equity_snapshots(snapshot_at);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with sensible defaults.

    `path=None` (the common case) resolves to the module-level
    `DEFAULT_DB_PATH` at call time, so tests can monkey-patch
    `ledger.DEFAULT_DB_PATH` before invoking `repo.*` helpers.

    - `row_factory = sqlite3.Row` so query results behave like dicts.
    - `PRAGMA foreign_keys = ON` because SQLite disables FKs by default for
       legacy reasons; we want them enforced.
    """
    p = path if path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(path: Path | None = None) -> None:
    """Create all tables and indexes if missing. Safe to call repeatedly.
    Also applies any in-flight migrations to existing databases."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


# Columns added after the initial schema. Listed as (column_name, ddl) pairs.
# `init_db` adds any missing ones; existing rows get NULL by default.
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "predictions": [
        ("confidence",         "TEXT"),
        ("input_tokens",       "INTEGER"),
        ("output_tokens",      "INTEGER"),
        ("cache_read_tokens",  "INTEGER"),
        ("cache_write_tokens", "INTEGER"),
        ("web_searches",       "INTEGER"),
        ("cost_usd",           "REAL"),
    ],
}


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive column migrations. SQLite has no IF NOT EXISTS for
    ALTER, so we PRAGMA-introspect each table and only add what's missing."""
    for table, columns in _MIGRATIONS.items():
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})")
        }
        for col_name, col_ddl in columns:
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_ddl}")


def main() -> None:
    print(f"initializing {DEFAULT_DB_PATH}")
    init_db()
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name"
        ).fetchall()
        print("schema objects:")
        for r in rows:
            print(f"  {r['name']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
