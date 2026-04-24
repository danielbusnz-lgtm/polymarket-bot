import asyncio
import json
import os
import sqlite3
import argparse
import time
from datetime import datetime, timezone

import requests

import db
from funnel import fetch_candidates
from strategies.llm import filter_politics, tier1_screen, tier2_analyze, print_provider_status

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
SIGNALS_DB_PATH = os.path.join(_PROJECT_ROOT, "paper_trades.db")
BOT_DB_PATH = os.path.join(_PROJECT_ROOT, "bot.db")
TRADE_SIZE = float(os.getenv("TRADE_SIZE", "10"))
GAMMA_API = "https://gamma-api.polymarket.com"

# ---------------------------------------------------------------------------
# Database helpers — signals (paper_trades.db)
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    return db.connect_signals(SIGNALS_DB_PATH)


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at        TEXT    NOT NULL,
                market_id     TEXT    NOT NULL,
                question      TEXT    NOT NULL,
                direction     TEXT    NOT NULL,
                token_id      TEXT    NOT NULL DEFAULT '',
                price         REAL    NOT NULL,
                edge          REAL    NOT NULL,
                avg_prob      REAL    NOT NULL,
                disagreement  REAL    NOT NULL,
                live          INTEGER DEFAULT 0,
                order_id      TEXT,
                fill_price    REAL,
                resolved      INTEGER DEFAULT 0,
                outcome       TEXT,
                correct       INTEGER,
                trade_size    REAL,
                realized_pnl  REAL
            )
        """)
        conn.commit()
        _migrate_signals(conn)


def _migrate_signals(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(signals)")}
    migrations = {
        "token_id":     "ALTER TABLE signals ADD COLUMN token_id     TEXT NOT NULL DEFAULT ''",
        "live":         "ALTER TABLE signals ADD COLUMN live         INTEGER DEFAULT 0",
        "order_id":     "ALTER TABLE signals ADD COLUMN order_id     TEXT",
        "fill_price":   "ALTER TABLE signals ADD COLUMN fill_price   REAL",
        "trade_size":   "ALTER TABLE signals ADD COLUMN trade_size   REAL",
        "realized_pnl": "ALTER TABLE signals ADD COLUMN realized_pnl REAL",
    }
    for col, sql in migrations.items():
        if col not in existing:
            conn.execute(sql)
    conn.commit()


# ---------------------------------------------------------------------------
# Database helpers — bot state (bot.db)
# ---------------------------------------------------------------------------


def get_bot_conn() -> sqlite3.Connection:
    return db.connect_bot(BOT_DB_PATH)


def init_bot_db() -> None:
    with get_bot_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                value     REAL NOT NULL,
                is_paper  INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL,
                direction     TEXT NOT NULL,
                amount_in     REAL NOT NULL,
                current_value REAL NOT NULL,
                our_prob      REAL NOT NULL,
                market_prob   REAL NOT NULL,
                opened_at     REAL NOT NULL,
                is_paper      INTEGER NOT NULL DEFAULT 0,
                token_id      TEXT NOT NULL DEFAULT '',
                entry_price   REAL NOT NULL DEFAULT 0,
                market_id     TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_runs (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at REAL NOT NULL
            )
        """)
        conn.commit()
        _migrate_positions(conn)


def _migrate_positions(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(positions)")}
    migrations = {
        "token_id":    "ALTER TABLE positions ADD COLUMN token_id    TEXT NOT NULL DEFAULT ''",
        "entry_price": "ALTER TABLE positions ADD COLUMN entry_price REAL NOT NULL DEFAULT 0",
        "market_id":   "ALTER TABLE positions ADD COLUMN market_id   TEXT NOT NULL DEFAULT ''",
    }
    for col, sql in migrations.items():
        if col not in existing:
            conn.execute(sql)
    conn.commit()


# ---------------------------------------------------------------------------
# Signal logging
# ---------------------------------------------------------------------------


def log_signal(signal: dict, trade_size: float) -> int:
    run_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO signals
                (run_at, market_id, question, direction, token_id, price, edge, avg_prob, disagreement, trade_size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_at,
            signal["market_id"],
            signal["question"],
            signal["direction"],
            signal.get("token_id", ""),
            signal["price"],
            signal["edge"],
            signal["avg_prob"],
            signal["disagreement"],
            trade_size,
        ))
        conn.commit()
        return cur.lastrowid


def mark_live(signal_id: int, order_id: str, fill_price: float | None = None) -> None:
    with get_conn() as conn:
        conn.execute("""
            UPDATE signals SET live = 1, order_id = ?, fill_price = ? WHERE id = ?
        """, (order_id, fill_price, signal_id))
        conn.commit()
    print(f"  Signal {signal_id} marked LIVE — order_id={order_id}")


def resolve_signal(signal_id: int, outcome: str) -> None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT direction, price, trade_size FROM signals WHERE id = ?", (signal_id,),
        ).fetchone()
        if not row:
            print(f"Signal {signal_id} not found.")
            return
        correct = 1 if row["direction"] == outcome else 0
        size = row["trade_size"] if row["trade_size"] is not None else TRADE_SIZE
        price = row["price"] or 0
        if correct and price > 0:
            pnl = size * (1.0 / price) - size
        else:
            pnl = -size
        conn.execute("""
            UPDATE signals SET resolved = 1, outcome = ?, correct = ?, realized_pnl = ? WHERE id = ?
        """, (outcome, correct, round(pnl, 2), signal_id))
        conn.commit()
    print(f"  Signal {signal_id}: direction={row['direction']} outcome={outcome} -> {'WIN' if correct else 'LOSS'}  pnl=${pnl:+.2f}")


# ---------------------------------------------------------------------------
# Position tracking (bot.db)
# ---------------------------------------------------------------------------


def position_size(signal: dict) -> float:
    # Kelly fraction f = (q - p) / (1 - p), capped at TRADE_SIZE.
    p = signal["price"]
    q = signal["avg_prob"]
    if p <= 0 or p >= 1 or q <= p:
        return 0.0
    kelly = (q - p) / (1.0 - p)
    return round(min(TRADE_SIZE, TRADE_SIZE * kelly), 2)


def _question_stem(question: str) -> str:
    return question[:30].strip().lower()


def has_open_position(market_id: str, direction: str) -> bool:
    with get_bot_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM positions WHERE market_id = ? AND direction = ? LIMIT 1",
            (market_id, direction),
        ).fetchone()
    return row is not None


def has_correlated_position(question: str, direction: str) -> bool:
    # Block trades whose question shares a prefix with an open position in the same direction.
    stem = _question_stem(question) + "%"
    with get_bot_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM positions WHERE LOWER(title) LIKE ? AND direction = ? LIMIT 1",
            (stem, direction),
        ).fetchone()
    return row is not None


def write_position(signal: dict, trade_size: float, is_paper: bool) -> None:
    with get_bot_conn() as conn:
        conn.execute("""
            INSERT INTO positions
                (title, direction, amount_in, current_value, our_prob, market_prob,
                 opened_at, is_paper, token_id, entry_price, market_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal["question"],
            signal["direction"],
            trade_size,
            trade_size,
            signal["avg_prob"],
            signal["price"],
            time.time(),
            1 if is_paper else 0,
            signal.get("token_id", ""),
            signal["price"],
            signal["market_id"],
        ))
        conn.commit()


# ---------------------------------------------------------------------------
# Price updater + portfolio snapshots
# ---------------------------------------------------------------------------


def update_prices() -> None:
    conn = get_bot_conn()
    positions = conn.execute("SELECT * FROM positions").fetchall()
    if not positions:
        conn.close()
        return

    token_ids = [p["token_id"] for p in positions if p["token_id"]]
    if not token_ids:
        conn.close()
        return

    # Batch fetch current midpoints
    prices = _fetch_midpoints(token_ids)

    now = time.time()
    live_value = 0.0
    paper_value = 0.0

    for p in positions:
        tid = p["token_id"]
        if tid not in prices or p["entry_price"] <= 0:
            if p["is_paper"]:
                paper_value += p["current_value"]
            else:
                live_value += p["current_value"]
            continue

        current_price = prices[tid]
        new_value = p["amount_in"] * (current_price / p["entry_price"])

        conn.execute("""
            UPDATE positions SET current_value = ?, market_prob = ? WHERE id = ?
        """, (round(new_value, 2), current_price, p["id"]))

        if p["is_paper"]:
            paper_value += new_value
        else:
            live_value += new_value

    # Write portfolio snapshots
    if live_value > 0:
        conn.execute(
            "INSERT INTO portfolio_snapshots (timestamp, value, is_paper) VALUES (?, ?, 0)",
            (now, round(live_value, 2)),
        )
    if paper_value > 0:
        conn.execute(
            "INSERT INTO portfolio_snapshots (timestamp, value, is_paper) VALUES (?, ?, 1)",
            (now, round(paper_value, 2)),
        )

    conn.commit()
    conn.close()
    print(f"Prices updated: live=${live_value:.2f}  paper=${paper_value:.2f}")


def _fetch_midpoints(token_ids: list[str]) -> dict[str, float]:
    import httpx
    payload = [{"token_id": tid} for tid in set(token_ids)]
    try:
        resp = httpx.post("https://clob.polymarket.com/midpoints", json=payload, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return {tid: float(data[tid]) for tid in data if data[tid]}
    except Exception as e:
        print(f"  [WARN] Failed to fetch midpoints: {e}")
        return {}


# ---------------------------------------------------------------------------
# Auto-resolve
# ---------------------------------------------------------------------------


def auto_resolve() -> None:
    conn = get_conn()
    unresolved = conn.execute(
        "SELECT id, market_id, direction FROM signals WHERE resolved = 0"
    ).fetchall()
    conn.close()

    if not unresolved:
        return

    # Group signals by market_id
    market_signals: dict[str, list[dict]] = {}
    for row in unresolved:
        mid = row["market_id"]
        if mid not in market_signals:
            market_signals[mid] = []
        market_signals[mid].append(dict(row))

    resolved_count = 0
    for market_id, signals in market_signals.items():
        winner = _check_resolution(market_id)
        if winner is None:
            continue

        outcome = winner.upper()  # "Yes" -> "YES", "No" -> "NO"
        for sig in signals:
            resolve_signal(sig["id"], outcome)
            resolved_count += 1

        # Remove resolved positions from bot.db
        bot_conn = get_bot_conn()
        bot_conn.execute("DELETE FROM positions WHERE market_id = ?", (market_id,))
        bot_conn.commit()
        bot_conn.close()

    if resolved_count:
        print(f"Auto-resolved {resolved_count} signals")


def _check_resolution(market_id: str) -> str | None:
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"condition_id": market_id},
            timeout=10,
        )
        resp.raise_for_status()
        markets = resp.json()
        if not markets:
            return None

        market = markets[0]
        if not market.get("closed"):
            return None

        outcomes = json.loads(market.get("outcomes", "[]"))
        prices = json.loads(market.get("outcomePrices", "[]"))

        winner = next(
            (outcomes[i] for i, p in enumerate(prices) if float(p) == 1.0),
            None,
        )
        return winner
    except Exception as e:
        print(f"  [WARN] Resolution check failed for {market_id[:12]}...: {e}")
        return None


# ---------------------------------------------------------------------------
# Live order placement
# ---------------------------------------------------------------------------


def place_order(signal: dict, trade_size: float) -> str | None:
    from client import get_client
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.order_builder.constants import BUY

    client = get_client()
    token_id = signal["token_id"]
    price = signal["price"]
    size = round(trade_size / price, 2)

    try:
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY,
        )
        resp = client.create_and_post_order(order_args)
        order_id = resp.get("orderID", "")
        print(f"  Order placed: {order_id}  size={size} shares @ {price}")
        return order_id
    except Exception as e:
        print(f"  [ERROR] Order placement failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def show_report() -> None:
    with get_conn() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        open_    = conn.execute("SELECT COUNT(*) FROM signals WHERE resolved = 0").fetchone()[0]
        live_    = conn.execute("SELECT COUNT(*) FROM signals WHERE live = 1").fetchone()[0]
        wins     = conn.execute("SELECT COUNT(*) FROM signals WHERE correct = 1").fetchone()[0]
        losses   = conn.execute("SELECT COUNT(*) FROM signals WHERE correct = 0").fetchone()[0]
        resolved = wins + losses

        print(f"\n{'='*50}")
        print(f"PAPER TRADE REPORT")
        print(f"{'='*50}")
        print(f"  Total signals : {total}")
        print(f"  Open          : {open_}")
        print(f"  Live orders   : {live_}")
        print(f"  Resolved      : {resolved}  (wins={wins}  losses={losses})")
        if resolved > 0:
            print(f"  Win rate      : {wins/resolved:.1%}")

        pnl_row = conn.execute(
            "SELECT SUM(realized_pnl) AS total, SUM(trade_size) AS staked FROM signals WHERE resolved = 1"
        ).fetchone()
        if pnl_row and pnl_row["total"] is not None:
            total_pnl = pnl_row["total"] or 0.0
            staked = pnl_row["staked"] or 0.0
            roi = (total_pnl / staked) if staked else 0.0
            print(f"  Realized P&L  : ${total_pnl:+.2f}  (staked ${staked:.2f}, ROI {roi:+.1%})")

        rows = conn.execute("""
            SELECT
                CASE
                    WHEN edge >= 0.20 THEN '20%+'
                    WHEN edge >= 0.15 THEN '15-20%'
                    ELSE               '12-15%'
                END AS bucket,
                COUNT(*) AS n,
                SUM(correct) AS w,
                SUM(realized_pnl) AS pnl
            FROM signals
            WHERE resolved = 1
            GROUP BY bucket
            ORDER BY bucket DESC
        """).fetchall()

        if rows:
            print(f"\n  Edge bucket breakdown:")
            for r in rows:
                wr = r["w"] / r["n"] if r["n"] else 0
                pnl = r["pnl"] or 0.0
                print(f"    {r['bucket']:10s}  n={r['n']}  win={wr:.1%}  pnl=${pnl:+.2f}")

        open_rows = conn.execute("""
            SELECT id, run_at, direction, question, price, edge, live, order_id
            FROM signals WHERE resolved = 0
            ORDER BY run_at DESC
        """).fetchall()
        if open_rows:
            print(f"\n  Open signals:")
            for r in open_rows:
                live_tag = f" [LIVE order={r['order_id']}]" if r["live"] else " [paper]"
                print(f"    [{r['id']}] {r['direction']} | edge={r['edge']:.2f} | price={r['price']:.2f}{live_tag} | {r['question'][:55]}")
        print()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(live: bool = False) -> None:
    # Validate LLM providers before starting
    print_provider_status()

    init_db()
    init_bot_db()

    # Log this cron run
    with get_bot_conn() as conn:
        conn.execute("INSERT INTO cron_runs (ran_at) VALUES (?)", (time.time(),))
        conn.commit()

    # Housekeeping: resolve closed markets, update prices
    print("Checking for resolved markets...")
    auto_resolve()

    print("Updating position prices...")
    update_prices()

    # Funnel
    candidates = fetch_candidates()
    if not candidates:
        print("No candidates found.")
        return

    candidates = await filter_politics(candidates)
    print(f"After AI filter: {len(candidates)} politics/world events markets")
    if not candidates:
        print("No politics/world events markets found.")
        return

    print(f"\nRunning Tier 1 screen on {len(candidates)} candidates...")
    picks = await tier1_screen(candidates)
    print(f"Tier 1 selected {len(picks)} markets for deep analysis")

    print("\nRunning Tier 2 analysis...")
    results = await asyncio.gather(*[tier2_analyze(m) for m in picks])

    trades = [r for r in results if r is not None]
    print(f"\n{'='*60}")
    print(f"TRADE SIGNALS: {len(trades)} found")
    print(f"{'='*60}")

    is_paper = not live
    seen_stems: set[tuple[str, str]] = set()

    # Take the highest-edge signal first so dedup keeps the strongest trade
    trades.sort(key=lambda x: x["edge"], reverse=True)

    for t in trades:
        if has_open_position(t["market_id"], t["direction"]):
            print(f"\n  SKIP {t['direction']} {t['question'][:70]} — already holding")
            continue

        stem_key = (_question_stem(t["question"]), t["direction"])
        if stem_key in seen_stems or has_correlated_position(t["question"], t["direction"]):
            print(f"\n  SKIP {t['direction']} {t['question'][:70]} — correlated trade already taken")
            continue
        seen_stems.add(stem_key)

        size = position_size(t)
        row_id = log_signal(t, size)
        print(f"\n  [{row_id}] {t['direction']} {t['question'][:70]}")
        print(f"       Price: {t['price']:.2f}  Edge: {t['edge']:.2f}  Avg prob: {t['avg_prob']:.2f}  Size: ${size:.2f}")

        # Write position to bot.db
        write_position(t, size, is_paper)

        # Place real order if live
        if live:
            order_id = place_order(t, size)
            if order_id:
                mark_live(row_id, order_id)

    if not trades:
        print("  None — check back next run.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Signum paper/live trading")
    sub = parser.add_subparsers(dest="cmd")

    run_parser = sub.add_parser("run", help="Run pipeline and log signals")
    run_parser.add_argument("--live", action="store_true", help="Place real orders on Polymarket")

    sub.add_parser("report", help="Print calibration report")

    res = sub.add_parser("resolve", help="Mark a signal resolved")
    res.add_argument("id",      type=int,              help="Signal ID")
    res.add_argument("outcome", choices=["YES", "NO"], help="Actual outcome")

    args = parser.parse_args()

    if args.cmd == "run" or args.cmd is None:
        live = getattr(args, "live", False)
        if live:
            print("*** LIVE MODE — real orders will be placed ***\n")
        asyncio.run(run_pipeline(live=live))
    elif args.cmd == "report":
        init_db()
        show_report()
    elif args.cmd == "resolve":
        init_db()
        resolve_signal(args.id, args.outcome)


if __name__ == "__main__":
    main()
