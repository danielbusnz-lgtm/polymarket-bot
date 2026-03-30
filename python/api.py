import os
import sqlite3
import time
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BOT_DB_PATH = os.environ.get("BOT_DB_PATH", "bot.db")
PAPER_TRADES_DB_PATH = os.environ.get("PAPER_TRADES_DB_PATH", "paper_trades.db")

CRON_INTERVAL_SECONDS = 6 * 3600

app = FastAPI(title="Signum Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _open_db(path: str) -> sqlite3.Connection | None:
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        return None


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


@app.get("/api/snapshots")
def get_snapshots(mode: str = Query(default="live", pattern="^(live|paper)$")) -> dict:
    is_paper = 1 if mode == "paper" else 0
    conn = _open_db(BOT_DB_PATH)
    if conn is None:
        return {"mode": mode, "snapshots": []}
    with conn:
        rows = conn.execute(
            "SELECT timestamp, value FROM portfolio_snapshots WHERE is_paper=? ORDER BY timestamp",
            (is_paper,),
        ).fetchall()
    return {"mode": mode, "snapshots": _rows_to_dicts(rows)}


@app.get("/api/positions")
def get_positions(mode: str = Query(default="live", pattern="^(live|paper)$")) -> dict:
    is_paper = 1 if mode == "paper" else 0
    conn = _open_db(BOT_DB_PATH)
    if conn is None:
        return {"mode": mode, "positions": []}
    with conn:
        rows = conn.execute(
            """
            SELECT title, direction, amount_in, current_value,
                   our_prob, market_prob, opened_at
            FROM positions
            WHERE is_paper=?
            """,
            (is_paper,),
        ).fetchall()
    return {"mode": mode, "positions": _rows_to_dicts(rows)}


@app.get("/api/signals")
def get_signals(
    status: str = Query(default="open", pattern="^(open|resolved|all)$"),
) -> dict:
    conn = _open_db(PAPER_TRADES_DB_PATH)
    if conn is None:
        return {"status": status, "signals": []}

    if status == "open":
        where = "WHERE resolved=0"
    elif status == "resolved":
        where = "WHERE resolved=1"
    else:
        where = ""

    with conn:
        rows = conn.execute(
            f"""
            SELECT id, run_at, market_id, question, direction, token_id,
                   price, edge, avg_prob, disagreement, live, order_id,
                   fill_price, resolved, outcome, correct
            FROM signals
            {where}
            ORDER BY run_at DESC
            """,
        ).fetchall()
    return {"status": status, "signals": _rows_to_dicts(rows)}


@app.get("/api/stats")
def get_stats() -> dict:
    conn = _open_db(PAPER_TRADES_DB_PATH)
    empty: dict[str, Any] = {
        "total": 0,
        "open": 0,
        "live": 0,
        "resolved": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "avg_edge": None,
        "edge_buckets": [],
    }
    if conn is None:
        return empty

    with conn:
        rows = conn.execute(
            "SELECT edge, live, resolved, correct FROM signals"
        ).fetchall()

    if not rows:
        return empty

    total = len(rows)
    open_count = sum(1 for r in rows if r["resolved"] == 0)
    live_count = sum(1 for r in rows if r["live"] == 1)
    resolved_rows = [r for r in rows if r["resolved"] == 1]
    resolved_count = len(resolved_rows)
    wins = sum(1 for r in resolved_rows if r["correct"] == 1)
    losses = sum(1 for r in resolved_rows if r["correct"] == 0)
    win_rate = (wins / resolved_count) if resolved_count > 0 else None
    edges = [r["edge"] for r in rows if r["edge"] is not None]
    avg_edge = sum(edges) / len(edges) if edges else None

    def _bucket_stats(lower: float, upper: float | None) -> dict:
        bucket_rows = [
            r for r in resolved_rows
            if r["edge"] is not None
            and r["edge"] >= lower
            and (upper is None or r["edge"] < upper)
        ]
        count = len(bucket_rows)
        bucket_wins = sum(1 for r in bucket_rows if r["correct"] == 1)
        return {
            "label": f"{int(lower * 100)}%+" if upper is None else f"{int(lower * 100)}-{int(upper * 100)}%",
            "count": count,
            "win_rate": (bucket_wins / count) if count > 0 else None,
        }

    edge_buckets = [
        _bucket_stats(0.12, 0.15),
        _bucket_stats(0.15, 0.20),
        _bucket_stats(0.20, None),
    ]

    return {
        "total": total,
        "open": open_count,
        "live": live_count,
        "resolved": resolved_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_edge": avg_edge,
        "edge_buckets": edge_buckets,
    }


@app.get("/api/cron")
def get_cron() -> dict:
    conn = _open_db(BOT_DB_PATH)
    if conn is None:
        return {"last_run": None, "seconds_until_next": None}
    with conn:
        row = conn.execute("SELECT MAX(ran_at) AS last_ran FROM cron_runs").fetchone()

    last_run = row["last_ran"] if row else None
    if last_run is None:
        return {"last_run": None, "seconds_until_next": None}

    now = time.time()
    next_run = last_run + CRON_INTERVAL_SECONDS
    seconds_until_next = max(0, int(next_run - now))
    return {"last_run": last_run, "seconds_until_next": seconds_until_next}


# ---------------------------------------------------------------------------
# Live prices from Polymarket CLOB
# ---------------------------------------------------------------------------

CLOB_BASE = "https://clob.polymarket.com"
PRICE_CACHE_TTL = 20  # seconds

_price_cache: dict[str, tuple[float, float]] = {}  # token_id -> (price, fetched_at)


def _fetch_midpoints(token_ids: list[str]) -> dict[str, float]:
    if not token_ids:
        return {}
    payload = [{"token_id": tid} for tid in token_ids]
    try:
        resp = httpx.post(f"{CLOB_BASE}/midpoints", json=payload, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        return {tid: float(data[tid]) for tid in data if data[tid]}
    except Exception:
        return {}


def _get_prices(token_ids: list[str]) -> dict[str, float]:
    now = time.time()
    result: dict[str, float] = {}
    stale: list[str] = []

    for tid in token_ids:
        if tid in _price_cache:
            price, fetched_at = _price_cache[tid]
            if now - fetched_at < PRICE_CACHE_TTL:
                result[tid] = price
                continue
        stale.append(tid)

    if stale:
        fresh = _fetch_midpoints(stale)
        for tid, price in fresh.items():
            _price_cache[tid] = (price, now)
            result[tid] = price

    return result


@app.get("/api/prices")
def get_prices(token_ids: str = Query(description="Comma separated token IDs")) -> dict:
    ids = [t.strip() for t in token_ids.split(",") if t.strip()]
    if not ids:
        return {"prices": {}}
    prices = _get_prices(ids)
    return {"prices": prices}
