"""Real-data integration test for repo.py helpers.

Spins up a fresh test database in a temp file, fetches one live market
from Polymarket Gamma, then exercises every repo function and verifies
the writes/reads behave correctly. Cleans up the temp DB on exit.

Run: .venv/bin/python tests/test_repo.py

Plain assertions, no pytest. Each step prints what passed so the trace
itself is the diagnostic.
"""

import sys
import tempfile
from pathlib import Path

# Source modules live at the project root, one level up from tests/.
sys.path.insert(0, str(Path(__file__).parent.parent))

# Swap the database path BEFORE importing repo, so all of repo's calls go
# to our test DB. ledger.connect() reads DEFAULT_DB_PATH at call time
# (see the lazy resolution in ledger.py), so monkey-patching here works.
_tmp = tempfile.NamedTemporaryFile(suffix=".signum-test.db", delete=False)
TEST_DB = Path(_tmp.name)
_tmp.close()

import ledger  # noqa: E402

ledger.DEFAULT_DB_PATH = TEST_DB
ledger.init_db()

import repo  # noqa: E402
from gamma import fetch_top_market  # noqa: E402


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(cond: bool, label: str) -> None:
    if not cond:
        raise AssertionError(f"{label}: assertion failed")


def main() -> None:
    print(f"using test db: {TEST_DB}\n")

    # ─── 1. fetch real data ────────────────────────────────────────────────
    market = fetch_top_market()
    print(f"1. fetched market: {market.question[:65]}...")
    print(f"   id={market.id} | accepting={market.accepting_orders}")

    # ─── 2. upsert_market: first call should insert ────────────────────────
    repo.upsert_market(market)
    with ledger.connect() as conn:
        row = conn.execute(
            "SELECT * FROM markets WHERE id = ?", (market.id,)
        ).fetchone()
    assert_true(row is not None, "market row should exist after upsert")
    assert_eq(row["question"], market.question, "question matches")
    assert_eq(row["condition_id"], market.condition_id, "condition_id matches")
    assert_eq(bool(row["neg_risk"]), market.neg_risk, "neg_risk roundtrip")
    first_seen_original = row["first_seen_at"]
    print(f"2. upsert_market: inserted (first_seen_at={first_seen_original})")

    # ─── 3. upsert_market again: first_seen_at preserved ───────────────────
    repo.upsert_market(market)
    with ledger.connect() as conn:
        row2 = conn.execute(
            "SELECT * FROM markets WHERE id = ?", (market.id,)
        ).fetchone()
    assert_eq(
        row2["first_seen_at"],
        first_seen_original,
        "first_seen_at preserved on second upsert",
    )
    with ledger.connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM markets").fetchone()["n"]
    assert_eq(n, 1, "still one market row, not two")
    print(f"3. upsert_market (2nd call): first_seen_at preserved, no duplicate row")

    # ─── 4. record_snapshot: pure append ───────────────────────────────────
    snap_id1 = repo.record_snapshot(market)
    snap_id2 = repo.record_snapshot(market)
    assert_true(snap_id2 > snap_id1, "snapshot ids increment")
    with ledger.connect() as conn:
        snaps = conn.execute(
            "SELECT * FROM market_snapshots WHERE market_id = ? ORDER BY id",
            (market.id,),
        ).fetchall()
    assert_eq(len(snaps), 2, "2 snapshot rows appended")
    print(f"4. record_snapshot: {len(snaps)} rows (ids {snap_id1}, {snap_id2})")

    # ─── 5. record_prediction: links snapshot + market ─────────────────────
    pred_id = repo.record_prediction(
        market_id=market.id,
        snapshot_id=snap_id2,
        yes_probability=0.42,
        model="test-model",
        prompt_version="v1",
        raw_response="0.42",
    )
    with ledger.connect() as conn:
        pred = conn.execute(
            "SELECT * FROM predictions WHERE id = ?", (pred_id,)
        ).fetchone()
    assert_eq(pred["yes_probability"], 0.42, "yes_probability stored")
    assert_eq(pred["snapshot_id"], snap_id2, "snapshot_id linked")
    assert_eq(pred["market_id"], market.id, "market_id linked")
    print(f"5. record_prediction: id={pred_id}, linked to snapshot #{snap_id2}")

    # ─── 6. place_paper_order: status starts 'open' ────────────────────────
    order_id = repo.place_paper_order(
        market_id=market.id,
        prediction_id=pred_id,
        outcome_index=0,
        side="buy",
        size=5.0,
        limit_price=0.01,
        reason="test",
    )
    with ledger.connect() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
    assert_eq(order["status"], "open", "order status='open'")
    assert_eq(order["side"], "buy", "side stored")
    assert_eq(order["size"], 5.0, "size stored")
    assert_eq(order["prediction_id"], pred_id, "prediction_id linked")
    print(f"6. place_paper_order: id={order_id}, status='open'")

    # ─── 7. invalid side rejected at the API boundary ──────────────────────
    raised = False
    try:
        repo.place_paper_order(
            market_id=market.id,
            prediction_id=None,
            outcome_index=0,
            side="invalid",
            size=1.0,
            limit_price=0.5,
        )
    except ValueError:
        raised = True
    assert_true(raised, "invalid side raises ValueError")
    print(f"7. place_paper_order: rejects invalid side ✓")

    # ─── 8. open_orders: returns our one open order ────────────────────────
    opens = repo.open_orders()
    assert_eq(len(opens), 1, "exactly 1 open order")
    assert_eq(opens[0]["id"], order_id, "matches what we placed")
    print(f"8. open_orders: {len(opens)} returned")

    # ─── 9. mark_filled: writes fill row + flips status atomically ─────────
    repo.mark_filled(order_id, price=0.01, size=5.0)
    with ledger.connect() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        fills = conn.execute(
            "SELECT * FROM fills WHERE order_id = ?", (order_id,)
        ).fetchall()
    assert_eq(order["status"], "filled", "status flipped to filled")
    assert_eq(len(fills), 1, "exactly 1 fill row written")
    assert_eq(fills[0]["price"], 0.01, "fill price stored")
    assert_eq(fills[0]["size"], 5.0, "fill size stored")
    print(f"9. mark_filled: order status='filled', 1 fill row")

    # ─── 10. open_orders empty after fill ──────────────────────────────────
    opens_after = repo.open_orders()
    assert_eq(len(opens_after), 0, "no open orders after fill")
    print(f"10. open_orders after fill: 0 (as expected)")

    # ─── 11. equity tracking ───────────────────────────────────────────────
    assert_true(repo.latest_equity() is None, "latest_equity is None on empty table")
    repo.record_equity(cash=95.0, open_positions_value=5.0, realized_pnl_cumulative=0.0)
    repo.record_equity(cash=90.0, open_positions_value=12.0, realized_pnl_cumulative=2.0)
    eq = repo.latest_equity()
    assert_true(eq is not None, "latest_equity returns a row")
    assert_eq(eq["cash"], 90.0, "latest cash is the second insert")
    assert_eq(eq["open_positions_value"], 12.0, "open_positions_value stored")
    assert_eq(eq["total_equity"], 102.0, "total_equity = cash + positions_value")
    print(f"11. record_equity + latest_equity: cash={eq['cash']}, total={eq['total_equity']}")

    # ─── 12. foreign keys actually enforced ────────────────────────────────
    raised = False
    try:
        with ledger.connect() as conn:
            conn.execute(
                "INSERT INTO fills (order_id, filled_at, price, size) "
                "VALUES (?, ?, ?, ?)",
                (999_999, "2026-01-01T00:00:00+00:00", 0.5, 1.0),
            )
    except Exception:
        raised = True
    assert_true(raised, "FK violation: orphan fill should be rejected")
    print(f"12. foreign keys: orphan fill rejected ✓")

    print("\n=== all 12 checks passed ===")


if __name__ == "__main__":
    try:
        main()
    finally:
        TEST_DB.unlink(missing_ok=True)
        print(f"\ncleaned up: {TEST_DB}")
