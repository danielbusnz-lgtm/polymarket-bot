"""
Migrate signals from python/paper_trades.db into bot.db.
Run from the project root: python3 migrate_signals.py
"""

import sqlite3

SRC  = "python/paper_trades.db"
DST  = "bot.db"

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

# Ensure signals table exists in bot.db
dst.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id            INTEGER PRIMARY KEY,
        run_at        TEXT    NOT NULL,
        market_id     TEXT    NOT NULL,
        question      TEXT    NOT NULL,
        direction     TEXT    NOT NULL,
        price         REAL    NOT NULL,
        edge          REAL    NOT NULL,
        avg_prob      REAL    NOT NULL,
        disagreement  REAL    NOT NULL,
        resolved      INTEGER NOT NULL DEFAULT 0,
        outcome       TEXT,
        correct       INTEGER,
        token_id      TEXT    NOT NULL DEFAULT ''
    )
""")

rows = src.execute("""
    SELECT run_at, market_id, question, direction, price, edge,
           avg_prob, disagreement, resolved, outcome, correct,
           COALESCE(token_id, '')
    FROM signals
    ORDER BY id ASC
""").fetchall()

dst.executemany("""
    INSERT INTO signals
        (run_at, market_id, question, direction, price, edge,
         avg_prob, disagreement, resolved, outcome, correct, token_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", rows)

dst.commit()
src.close()
dst.close()

print(f"Migrated {len(rows)} signals from {SRC} into {DST}")
