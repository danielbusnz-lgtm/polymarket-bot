"""Seed both SQLite databases with realistic mock data for development."""

import os
import random
import sqlite3
import time
import uuid

import db

random.seed(42)

BOT_DB_PATH = os.environ.get("BOT_DB_PATH", "bot.db")
PAPER_TRADES_DB_PATH = os.environ.get("PAPER_TRADES_DB_PATH", "paper_trades.db")

QUESTIONS = [
    "Will the Federal Reserve cut rates in Q2 2026?",
    "Will Ukraine and Russia sign a ceasefire before July 2026?",
    "Will the S&P 500 close above 6000 by end of June 2026?",
    "Will SpaceX successfully land Starship on the Moon before 2027?",
    "Will Elon Musk leave his White House role before August 2026?",
    "Will the UK rejoin the EU customs union by 2028?",
    "Will inflation in the US exceed 4% in 2026?",
    "Will China invade Taiwan before 2028?",
    "Will there be a US recession declared in 2026?",
    "Will the Democratic Party win the 2026 midterm Senate majority?",
    "Will Apple release an AR headset under $2000 in 2026?",
    "Will OpenAI release GPT-5 before September 2026?",
    "Will oil prices exceed $100 per barrel in 2026?",
    "Will the UN Security Council pass a Gaza ceasefire resolution in 2026?",
    "Will Anthropic achieve AGI safety certification from any body by 2027?",
    "Will Bitcoin exceed $150k before end of 2026?",
    "Will a major US bank fail in 2026?",
    "Will Kamala Harris run for office again in 2026?",
    "Will the US dollar index fall below 90 in 2026?",
    "Will there be a Category 5 hurricane hitting the US mainland in 2026?",
]

OUTCOMES = ["YES", "NO"]


def _now_unix() -> float:
    return time.time()


def _unix_days_ago(days: float) -> float:
    return _now_unix() - (days * 86400)


def seed_bot_db() -> None:
    conn = db.connect_bot(BOT_DB_PATH)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
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
                is_paper      INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cron_runs (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                ran_at REAL NOT NULL
            )
        """)

    with conn:
        conn.execute("DELETE FROM portfolio_snapshots")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM cron_runs")

    snapshots = []
    for mode, is_paper in [("live", 0), ("paper", 1)]:
        value = 1000.0
        for day in range(60, 0, -1):
            ts = _unix_days_ago(day)
            drift = random.gauss(0.0015, 0.012)
            value = max(200.0, value * (1 + drift))
            snapshots.append((ts, round(value, 2), is_paper))

    with conn:
        conn.executemany(
            "INSERT INTO portfolio_snapshots (timestamp, value, is_paper) VALUES (?, ?, ?)",
            snapshots,
        )

    positions = []
    used_questions = random.sample(QUESTIONS, 12)
    for i, question in enumerate(used_questions):
        is_paper = 1 if i >= 6 else 0
        direction = random.choice(["YES", "NO"])
        amount_in = round(random.uniform(50, 500), 2)
        pnl_factor = random.uniform(0.80, 1.35)
        current_value = round(amount_in * pnl_factor, 2)
        our_prob = round(random.uniform(0.52, 0.85), 3)
        market_prob = round(our_prob - random.uniform(0.08, 0.22), 3)
        opened_at = _unix_days_ago(random.uniform(1, 30))
        positions.append((
            question, direction, amount_in, current_value,
            our_prob, market_prob, opened_at, is_paper,
        ))

    with conn:
        conn.executemany(
            """
            INSERT INTO positions
                (title, direction, amount_in, current_value, our_prob, market_prob, opened_at, is_paper)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            positions,
        )

    cron_times = []
    for i in range(5):
        ran_at = _unix_days_ago(0) - (i * 6 * 3600) - random.uniform(0, 300)
        cron_times.append((ran_at,))

    with conn:
        conn.executemany("INSERT INTO cron_runs (ran_at) VALUES (?)", cron_times)

    conn.close()
    print(f"bot.db seeded: 120 snapshots, 12 positions, 5 cron runs -> {BOT_DB_PATH}")


def seed_paper_trades_db() -> None:
    conn = db.connect_signals(PAPER_TRADES_DB_PATH)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at       TEXT    NOT NULL,
                market_id    TEXT    NOT NULL,
                question     TEXT    NOT NULL,
                direction    TEXT    NOT NULL,
                token_id     TEXT    NOT NULL DEFAULT '',
                price        REAL    NOT NULL,
                edge         REAL    NOT NULL,
                avg_prob     REAL    NOT NULL,
                disagreement REAL    NOT NULL,
                live         INTEGER DEFAULT 0,
                order_id     TEXT,
                fill_price   REAL,
                resolved     INTEGER DEFAULT 0,
                outcome      TEXT,
                correct      INTEGER
            )
        """)
        conn.execute("DELETE FROM signals")

    signals = []

    for i in range(150):
        days_ago = random.uniform(1, 59)
        ts = _unix_days_ago(days_ago)
        from datetime import datetime, timezone
        run_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        question = random.choice(QUESTIONS)
        direction = random.choice(OUTCOMES)
        price = round(random.uniform(0.30, 0.75), 3)
        edge = round(random.uniform(0.10, 0.30), 4)
        avg_prob = round(price + edge + random.uniform(0, 0.05), 3)
        disagreement = round(random.uniform(0.05, 0.25), 3)
        is_live = 1 if random.random() < 0.3 else 0
        order_id = str(uuid.uuid4()) if is_live else None
        fill_price = round(price + random.uniform(-0.02, 0.02), 3) if is_live else None

        correct = 1 if random.random() < 0.63 else 0
        outcome = direction if correct else ("NO" if direction == "YES" else "YES")

        signals.append((
            run_at,
            f"market_{uuid.uuid4().hex[:12]}",
            question,
            direction,
            uuid.uuid4().hex[:16],
            price,
            edge,
            avg_prob,
            disagreement,
            is_live,
            order_id,
            fill_price,
            1,
            outcome,
            correct,
        ))

    for i in range(50):
        days_ago = random.uniform(0, 3)
        ts = _unix_days_ago(days_ago)
        from datetime import datetime, timezone
        run_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        question = random.choice(QUESTIONS)
        direction = random.choice(OUTCOMES)
        price = round(random.uniform(0.30, 0.75), 3)
        edge = round(random.uniform(0.10, 0.30), 4)
        avg_prob = round(price + edge + random.uniform(0, 0.05), 3)
        disagreement = round(random.uniform(0.05, 0.25), 3)
        is_live = 1 if random.random() < 0.25 else 0
        order_id = str(uuid.uuid4()) if is_live else None
        fill_price = round(price + random.uniform(-0.02, 0.02), 3) if is_live else None

        signals.append((
            run_at,
            f"market_{uuid.uuid4().hex[:12]}",
            question,
            direction,
            uuid.uuid4().hex[:16],
            price,
            edge,
            avg_prob,
            disagreement,
            is_live,
            order_id,
            fill_price,
            0,
            None,
            None,
        ))

    with conn:
        conn.executemany(
            """
            INSERT INTO signals
                (run_at, market_id, question, direction, token_id, price, edge,
                 avg_prob, disagreement, live, order_id, fill_price,
                 resolved, outcome, correct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            signals,
        )

    conn.close()
    print(f"paper_trades.db seeded: 200 signals (150 resolved, 50 open) -> {PAPER_TRADES_DB_PATH}")


if __name__ == "__main__":
    seed_bot_db()
    seed_paper_trades_db()
