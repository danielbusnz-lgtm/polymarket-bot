"""Thin data-access layer over the SQLite ledger.

One function per common read or write. Each function handles its own
connect/commit/close so callers can't forget the unsafe parts.

For one-off / analytics queries, prefer inline SQL in a script — these
helpers are for things the trading loop hits every cycle.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from ledger import connect
from market import Market


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------

def upsert_market(market: Market) -> None:
    """Insert a market if new; refresh mutable fields if already known.

    Preserves `first_seen_at` and any resolution columns once set.
    """
    now = _now_iso()
    conn = connect()
    try:
        with conn:
            conn.execute(
                """INSERT INTO markets
                   (id, condition_id, question, slug, end_date, outcomes,
                    neg_risk, first_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                       question  = excluded.question,
                       slug      = excluded.slug,
                       end_date  = excluded.end_date,
                       outcomes  = excluded.outcomes""",
                (
                    market.id,
                    market.condition_id,
                    market.question,
                    market.slug,
                    market.end_date.isoformat() if market.end_date else None,
                    json.dumps(market.outcomes),
                    1 if market.neg_risk else 0,
                    now,
                ),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Market snapshots
# ---------------------------------------------------------------------------

def record_snapshot(market: Market) -> int:
    """Log the current state of `market` and return the new snapshot row id."""
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO market_snapshots
                   (market_id, snapshot_at, outcome_prices,
                    volume_24hr, liquidity, accepting_orders)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    market.id,
                    _now_iso(),
                    json.dumps(market.outcome_prices),
                    market.volume_24hr,
                    market.liquidity,
                    1 if market.accepting_orders else 0,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def record_prediction(
    market_id: str,
    snapshot_id: int | None,
    yes_probability: float,
    model: str,
    prompt_version: str,
    raw_response: str | None = None,
    confidence: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    web_searches: int | None = None,
    cost_usd: float | None = None,
) -> int:
    """Log a Claude prediction. Returns the new prediction id.

    Token/cost fields are optional so old callers keep working, but
    populating them is how we track AI spend over time.
    """
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO predictions
                   (market_id, snapshot_id, predicted_at, model,
                    prompt_version, yes_probability, confidence, raw_response,
                    input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens,
                    web_searches, cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    market_id,
                    snapshot_id,
                    _now_iso(),
                    model,
                    prompt_version,
                    yes_probability,
                    confidence,
                    raw_response,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    web_searches,
                    cost_usd,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def market_ids_predicted_recently(within_hours: float = 24.0) -> set[str]:
    """Set of market_ids that have a prediction newer than `within_hours`.

    Used by the trading loop to skip re-scanning markets we already spent
    Claude tokens on. Pass `within_hours=4` for an aggressive trading loop,
    or `within_hours=24*7` to only re-scan weekly.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT market_id FROM predictions "
            "WHERE predicted_at >= ?",
            (cutoff.isoformat(),),
        ).fetchall()
        return {r["market_id"] for r in rows}
    finally:
        conn.close()


def total_ai_cost() -> float:
    """Sum of cost_usd across all predictions. Used for net P&L."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM predictions"
        ).fetchone()
        return float(row["total"])
    finally:
        conn.close()


def cost_summary() -> dict[str, float | int]:
    """Breakdown for quick reporting: total cost, per-model cost, counts."""
    conn = connect()
    try:
        row = conn.execute(
            """SELECT
                   COUNT(*) AS n_predictions,
                   COALESCE(SUM(cost_usd), 0.0) AS total_cost,
                   COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                   COALESCE(SUM(web_searches), 0) AS total_searches
               FROM predictions"""
        ).fetchone()
        per_model = conn.execute(
            """SELECT model,
                      COUNT(*) AS n,
                      COALESCE(SUM(cost_usd), 0.0) AS cost
               FROM predictions
               GROUP BY model
               ORDER BY cost DESC"""
        ).fetchall()
        return {
            "n_predictions": int(row["n_predictions"]),
            "total_cost_usd": float(row["total_cost"]),
            "total_input_tokens": int(row["total_input_tokens"]),
            "total_output_tokens": int(row["total_output_tokens"]),
            "total_web_searches": int(row["total_searches"]),
            "per_model": [
                {"model": r["model"], "n": int(r["n"]), "cost_usd": float(r["cost"])}
                for r in per_model
            ],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orders & fills
# ---------------------------------------------------------------------------

def place_paper_order(
    market_id: str,
    prediction_id: int | None,
    outcome_index: int,
    side: str,
    size: float,
    limit_price: float,
    reason: str = "",
) -> int:
    """Record a virtual order; status starts as 'open'. Returns the order id."""
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    conn = connect()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO orders
                   (market_id, prediction_id, outcome_index, side, size,
                    limit_price, placed_at, status, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)""",
                (
                    market_id,
                    prediction_id,
                    outcome_index,
                    side,
                    size,
                    limit_price,
                    _now_iso(),
                    reason,
                ),
            )
            return cur.lastrowid
    finally:
        conn.close()


def open_orders() -> list[sqlite3.Row]:
    """All paper orders still in 'open' state, oldest first."""
    conn = connect()
    try:
        return list(conn.execute(
            "SELECT * FROM orders WHERE status = 'open' ORDER BY placed_at"
        ))
    finally:
        conn.close()


def mark_filled(
    order_id: int,
    price: float,
    size: float,
    filled_at: datetime | None = None,
) -> None:
    """Record a fill against an open order and flip status to 'filled'.

    Atomic via the `with conn:` block — both the fill insert and the
    order update commit together or not at all.
    """
    when = (filled_at or datetime.now(timezone.utc)).isoformat()
    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO fills (order_id, filled_at, price, size) "
                "VALUES (?, ?, ?, ?)",
                (order_id, when, price, size),
            )
            conn.execute(
                "UPDATE orders SET status = 'filled' WHERE id = ?",
                (order_id,),
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Equity (P&L over time)
# ---------------------------------------------------------------------------

def record_equity(
    cash: float,
    open_positions_value: float,
    realized_pnl_cumulative: float,
) -> None:
    """Log one row of the equity curve. total_equity is derived."""
    total = cash + open_positions_value
    conn = connect()
    try:
        with conn:
            conn.execute(
                """INSERT INTO equity_snapshots
                   (snapshot_at, cash, open_positions_value,
                    realized_pnl_cumulative, total_equity)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    _now_iso(),
                    cash,
                    open_positions_value,
                    realized_pnl_cumulative,
                    total,
                ),
            )
    finally:
        conn.close()


def latest_equity() -> sqlite3.Row | None:
    """Most recent equity_snapshots row, or None if empty."""
    conn = connect()
    try:
        return conn.execute(
            "SELECT * FROM equity_snapshots "
            "ORDER BY snapshot_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
