"""Pure-logic tests — no LLM/Polymarket calls."""

import os
import sys
import tempfile

import pytest

# Make the python/ directory importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolated_dbs(monkeypatch):
    """Point each test at fresh temp SQLite files; ignore any TURSO_* env."""
    tmp = tempfile.mkdtemp()
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TURSO_SIGNALS_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_BOT_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_SIGNALS_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TURSO_BOT_AUTH_TOKEN", raising=False)

    # Import after env is clean so the module reads fresh values
    import paper_trade
    monkeypatch.setattr(paper_trade, "SIGNALS_DB_PATH", os.path.join(tmp, "signals.db"))
    monkeypatch.setattr(paper_trade, "BOT_DB_PATH", os.path.join(tmp, "bot.db"))
    paper_trade.init_db()
    paper_trade.init_bot_db()
    yield
    # tempfile.mkdtemp dirs are not auto-cleaned but the test runner exits.


# ---------------------------------------------------------------------------
# Position sizing (Kelly)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("price, prob, expected", [
    (0.06, 0.94, 9.36),       # huge edge -> ~max
    (0.40, 0.55, 2.50),       # marginal edge
    (0.50, 0.50, 0.0),        # no edge
    (0.60, 0.40, 0.0),        # negative edge
    (0.0,  0.50, 0.0),        # invalid price
    (1.0,  0.50, 0.0),        # invalid price
])
def test_position_size(price, prob, expected):
    from paper_trade import position_size
    assert position_size({"price": price, "avg_prob": prob}) == pytest.approx(expected, abs=0.01)


def test_position_size_capped_at_trade_size():
    from paper_trade import position_size, TRADE_SIZE
    # Pick numbers where Kelly > 1.0 to make sure we cap
    assert position_size({"price": 0.01, "avg_prob": 0.99}) <= TRADE_SIZE


# ---------------------------------------------------------------------------
# P&L computation on resolve
# ---------------------------------------------------------------------------


def test_resolve_winner_pnl():
    from paper_trade import log_signal, resolve_signal, get_conn
    sig_id = log_signal({
        "market_id": "m1", "question": "test", "direction": "YES",
        "price": 0.25, "edge": 0.5, "avg_prob": 0.75, "disagreement": 0.05,
    }, trade_size=10.0)
    resolve_signal(sig_id, "YES")
    with get_conn() as conn:
        row = conn.execute("SELECT correct, realized_pnl FROM signals WHERE id=?", (sig_id,)).fetchone()
    assert row["correct"] == 1
    # 10 / 0.25 - 10 = 30 profit
    assert row["realized_pnl"] == pytest.approx(30.0, abs=0.01)


def test_resolve_loser_pnl():
    from paper_trade import log_signal, resolve_signal, get_conn
    sig_id = log_signal({
        "market_id": "m2", "question": "test2", "direction": "YES",
        "price": 0.25, "edge": 0.5, "avg_prob": 0.75, "disagreement": 0.05,
    }, trade_size=10.0)
    resolve_signal(sig_id, "NO")
    with get_conn() as conn:
        row = conn.execute("SELECT correct, realized_pnl FROM signals WHERE id=?", (sig_id,)).fetchone()
    assert row["correct"] == 0
    assert row["realized_pnl"] == pytest.approx(-10.0, abs=0.01)


# ---------------------------------------------------------------------------
# Concentration / dedup
# ---------------------------------------------------------------------------


def test_correlated_position_dedup():
    from paper_trade import write_position, has_correlated_position, has_open_position

    write_position({
        "question": "US x Iran diplomatic meeting by April 25, 2026?",
        "direction": "YES", "avg_prob": 0.94, "price": 0.06,
        "token_id": "tok1", "market_id": "m1",
    }, trade_size=10.0, is_paper=True)

    # Same question stem, different market_id -> blocked by correlated check
    assert has_correlated_position("US x Iran diplomatic meeting by April 27, 2026?", "YES") is True
    # Same direction, different topic -> not blocked
    assert has_correlated_position("Will the Fed cut rates?", "YES") is False
    # Same exact market -> blocked by exact dedup
    assert has_open_position("m1", "YES") is True
    # Opposite direction same market -> not blocked (intentional, you may want both)
    assert has_open_position("m1", "NO") is False


# ---------------------------------------------------------------------------
# Edge bucket sums (report query)
# ---------------------------------------------------------------------------


def test_report_aggregates_pnl():
    from paper_trade import log_signal, resolve_signal, get_conn

    s1 = log_signal({"market_id": "a", "question": "q1", "direction": "YES",
                     "price": 0.10, "edge": 0.25, "avg_prob": 0.35, "disagreement": 0.05},
                    trade_size=10.0)
    resolve_signal(s1, "YES")  # +90
    s2 = log_signal({"market_id": "b", "question": "q2", "direction": "YES",
                     "price": 0.10, "edge": 0.25, "avg_prob": 0.35, "disagreement": 0.05},
                    trade_size=10.0)
    resolve_signal(s2, "NO")   # -10

    with get_conn() as conn:
        row = conn.execute("SELECT SUM(realized_pnl) AS total FROM signals WHERE resolved=1").fetchone()
    assert row["total"] == pytest.approx(80.0, abs=0.01)
