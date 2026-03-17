import asyncio
import sqlite3
import argparse
from datetime import datetime, timezone

from funnel import fetch_candidates
from strategies.llm import filter_politics, tier1_screen, tier2_analyze

DB_PATH = "paper_trades.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn



def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at        TEXT    NOT NULL,
                market_id     TEXT    NOT NULL,
                question      TEXT    NOT NULL,
                direction     TEXT    NOT NULL,
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


def log_signal(signal: dict) -> int:
    run_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO signals
                (run_at, market_id, question, direction, price, edge, avg_prob, disagreement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_at,
            signal["market_id"],
            signal["question"],
            signal["direction"],
            signal["price"],
            signal["edge"],
            signal["avg_prob"],
            signal["disagreement"],
        ))
        conn.commit()
        return cur.lastrowid


def resolve_signal(signal_id: int, outcome: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT direction FROM signals WHERE id = ?", (signal_id,)).fetchone()
        if not row:
            print(f"Signal {signal_id} not found.")
            return
        correct = 1 if row["direction"] == outcome else 0
        conn.execute("""
            UPDATE signals SET resolved = 1, outcome = ?, correct = ? WHERE id = ?
        """, (outcome, correct, signal_id))
        conn.commit()
    print(f"Signal {signal_id}: direction={row['direction']} outcome={outcome} → {'WIN' if correct else 'LOSS'}")


def show_report() -> None:
    with get_conn() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        open_    = conn.execute("SELECT COUNT(*) FROM signals WHERE resolved = 0").fetchone()[0]
        wins     = conn.execute("SELECT COUNT(*) FROM signals WHERE correct = 1").fetchone()[0]
        losses   = conn.execute("SELECT COUNT(*) FROM signals WHERE correct = 0").fetchone()[0]
        resolved = wins + losses

        print(f"\n{'='*50}")
        print(f"PAPER TRADE REPORT")
        print(f"{'='*50}")
        print(f"  Total signals : {total}")
        print(f"  Open          : {open_}")
        print(f"  Resolved      : {resolved}  (wins={wins}  losses={losses})")
        if resolved > 0:
            print(f"  Win rate      : {wins/resolved:.1%}")

        rows = conn.execute("""
            SELECT
                CASE
                    WHEN edge >= 0.20 THEN '20%+'
                    WHEN edge >= 0.15 THEN '15-20%'
                    ELSE               '12-15%'
                END AS bucket,
                COUNT(*) AS n,
                SUM(correct) AS w
            FROM signals
            WHERE resolved = 1
            GROUP BY bucket
            ORDER BY bucket DESC
        """).fetchall()

        if rows:
            print(f"\n  Edge bucket breakdown:")
            for r in rows:
                wr = r["w"] / r["n"] if r["n"] else 0
                print(f"    {r['bucket']:10s}  n={r['n']}  win={wr:.1%}")

        open_rows = conn.execute("""
            SELECT id, run_at, direction, question, price, edge
            FROM signals WHERE resolved = 0
            ORDER BY run_at DESC
        """).fetchall()
        if open_rows:
            print(f"\n  Open signals:")
            for r in open_rows:
                print(f"    [{r['id']}] {r['direction']} | edge={r['edge']:.2f} | price={r['price']:.2f} | {r['question'][:60]}")
        print()


async def run_pipeline() -> None:
    init_db()

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

    for t in trades:
        row_id = log_signal(t)
        print(f"\n  [{row_id}] {t['direction']} {t['question'][:70]}")
        print(f"       Price: {t['price']:.2f}  Edge: {t['edge']:.2f}  Avg prob: {t['avg_prob']:.2f}")

    if not trades:
        print("  None — check back next run.")


def main():
    parser = argparse.ArgumentParser(description="Polymarket paper trading")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run",    help="Run pipeline and log signals")
    sub.add_parser("report", help="Print calibration report")

    res = sub.add_parser("resolve", help="Mark a signal resolved")
    res.add_argument("id",      type=int,              help="Signal ID")
    res.add_argument("outcome", choices=["YES", "NO"], help="Actual outcome")

    args = parser.parse_args()

    if args.cmd == "run" or args.cmd is None:
        asyncio.run(run_pipeline())
    elif args.cmd == "report":
        init_db()
        show_report()
    elif args.cmd == "resolve":
        init_db()
        resolve_signal(args.id, args.outcome)


if __name__ == "__main__":
    main()
