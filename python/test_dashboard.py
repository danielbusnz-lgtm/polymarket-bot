"""
Inserts fake resolved trades into paper_trades.db every second.
Run this in one terminal while the dashboard is open in another.
Press Ctrl+C to stop. Cleans up the fake rows on exit.
"""
import sqlite3
import time
import random
import signal
import sys

DB = "python/paper_trades.db"

FAKE_MARKETS = [
    ("Will Trump sign the bill by April?",    "YES", 0.35, 0.25, 0.60),
    ("Will Fed cut rates in May?",            "YES", 0.60, 0.20, 0.80),
    ("Will Bitcoin hit $90k in April?",       "YES", 0.45, 0.15, 0.60),
    ("Will Ukraine ceasefire by June?",       "NO",  0.30, 0.18, 0.55),
    ("Will Macron resign by end of year?",    "NO",  0.20, 0.22, 0.35),
    ("Will US enter recession in 2026?",      "YES", 0.55, 0.14, 0.70),
    ("Will NATO add new member by July?",     "YES", 0.40, 0.30, 0.72),
    ("Will China invade Taiwan by 2027?",     "NO",  0.15, 0.20, 0.28),
]

inserted_ids = []

def cleanup(sig=None, frame=None):
    if inserted_ids:
        conn = sqlite3.connect(DB)
        ids  = ",".join("?" * len(inserted_ids))
        conn.execute(f"DELETE FROM signals WHERE id IN ({ids})", inserted_ids)
        conn.commit()
        conn.close()
        print(f"\nCleaned up {len(inserted_ids)} fake rows.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

conn = sqlite3.connect(DB)
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
        resolved      INTEGER DEFAULT 0,
        outcome       TEXT,
        correct       INTEGER
    )
""")
conn.commit()
conn.close()

print("Inserting fake trades every second — open the dashboard to watch the equity curve grow.")
print("Press Ctrl+C to stop and clean up.\n")

i = 0
while True:
    market = FAKE_MARKETS[i % len(FAKE_MARKETS)]
    question, direction, price, edge, avg_prob = market

    # 65% win rate to simulate a decent strategy
    correct = 1 if random.random() < 0.65 else 0
    outcome = direction if correct else ("NO" if direction == "YES" else "YES")

    conn = sqlite3.connect(DB)
    cur  = conn.execute("""
        INSERT INTO signals
            (run_at, market_id, question, direction, token_id, price, edge, avg_prob, disagreement,
             resolved, outcome, correct)
        VALUES (datetime('now'), ?, ?, ?, '', ?, ?, ?, 0.05, 1, ?, ?)
    """, (f"test-{i}", question, direction, price, edge, avg_prob, outcome, correct))
    conn.commit()
    inserted_ids.append(cur.lastrowid)
    conn.close()

    result = "WIN" if correct else "LOSS"
    print(f"[{i+1:3d}] {result}  {direction} {question[:50]}  edge={edge:.0%}")

    i += 1
    time.sleep(1)
