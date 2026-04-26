"""Tests for the isotonic calibration layer."""

import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _isolated_dbs(monkeypatch):
    tmp = tempfile.mkdtemp()
    for var in ("TURSO_AUTH_TOKEN", "TURSO_SIGNALS_DATABASE_URL", "TURSO_BOT_DATABASE_URL",
                "TURSO_SIGNALS_AUTH_TOKEN", "TURSO_BOT_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    import paper_trade
    monkeypatch.setattr(paper_trade, "SIGNALS_DB_PATH", os.path.join(tmp, "signals.db"))
    monkeypatch.setattr(paper_trade, "BOT_DB_PATH", os.path.join(tmp, "bot.db"))
    paper_trade.init_db()
    paper_trade.init_bot_db()
    yield


# ---------------------------------------------------------------------------
# Calibrator core
# ---------------------------------------------------------------------------


def test_identity_calibrator_passes_through():
    from calibration import Calibrator
    iso = Calibrator.identity()
    assert iso.predict(0.05) == pytest.approx(0.05)
    assert iso.predict(0.50) == pytest.approx(0.50)
    assert iso.predict(0.95) == pytest.approx(0.95)
    assert iso.is_identity is True


def test_identity_clips_to_unit_interval():
    from calibration import Calibrator
    iso = Calibrator.identity()
    assert 0.0 <= iso.predict(-0.5) <= 1.0
    assert 0.0 <= iso.predict(1.5) <= 1.0


def test_from_resolved_with_overconfident_model():
    """Model says 0.95 but only 70% are correct -> calibrator should map 0.95 -> ~0.7."""
    from calibration import Calibrator
    samples = []
    # 100 signals at prob=0.95, 70 win
    samples.extend([(0.95, 1)] * 70)
    samples.extend([(0.95, 0)] * 30)
    # 100 signals at prob=0.50, 50 win  (calibrated)
    samples.extend([(0.50, 1)] * 50)
    samples.extend([(0.50, 0)] * 50)
    # 100 signals at prob=0.05, 5 win   (calibrated)
    samples.extend([(0.05, 1)] * 5)
    samples.extend([(0.05, 0)] * 95)

    iso = Calibrator.from_resolved(samples)
    assert iso.is_identity is False
    assert iso.predict(0.95) == pytest.approx(0.70, abs=0.05)
    assert iso.predict(0.50) == pytest.approx(0.50, abs=0.05)
    assert iso.predict(0.05) == pytest.approx(0.05, abs=0.05)


def test_calibrator_is_monotonic_non_decreasing():
    from calibration import Calibrator
    # Noisy but trending: model is overconfident at every level
    import random
    rng = random.Random(42)
    samples = []
    for raw_p in [0.1, 0.3, 0.5, 0.7, 0.9]:
        true_p = 0.5 + (raw_p - 0.5) * 0.6  # shrink toward 0.5
        for _ in range(40):
            samples.append((raw_p, 1 if rng.random() < true_p else 0))
    iso = Calibrator.from_resolved(samples)
    xs = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    ys = [iso.predict(x) for x in xs]
    for a, b in zip(ys, ys[1:]):
        assert b + 1e-9 >= a, f"non-monotonic: {ys}"


def test_predict_clips_to_safe_bounds():
    """Should never output 0.0 or 1.0 — would break Kelly division."""
    from calibration import Calibrator
    samples = [(0.99, 1)] * 50 + [(0.01, 0)] * 50  # perfectly calibrated extremes
    iso = Calibrator.from_resolved(samples)
    assert iso.predict(0.99) <= 0.98
    assert iso.predict(0.01) >= 0.02


def test_from_resolved_too_few_samples_returns_identity():
    from calibration import Calibrator, MIN_SAMPLES
    samples = [(0.5, 1)] * (MIN_SAMPLES - 1)
    iso = Calibrator.from_resolved(samples)
    assert iso.is_identity is True


def test_from_resolved_empty_returns_identity():
    from calibration import Calibrator
    iso = Calibrator.from_resolved([])
    assert iso.is_identity is True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip():
    from calibration import Calibrator, save, load_latest
    import paper_trade

    samples = [(0.9, 1)] * 30 + [(0.9, 0)] * 30 + [(0.5, 1)] * 30 + [(0.5, 0)] * 30
    iso = Calibrator.from_resolved(samples)

    with paper_trade.get_bot_conn() as conn:
        save(conn, iso)

    with paper_trade.get_bot_conn() as conn:
        loaded = load_latest(conn)

    for x in [0.1, 0.5, 0.9]:
        assert loaded.predict(x) == pytest.approx(iso.predict(x), abs=1e-6)


def test_load_latest_with_no_fits_returns_identity():
    from calibration import load_latest
    import paper_trade
    with paper_trade.get_bot_conn() as conn:
        iso = load_latest(conn)
    assert iso.is_identity is True


def test_load_latest_picks_most_recent_fit():
    from calibration import Calibrator, save, load_latest
    import paper_trade

    older = Calibrator.from_resolved([(0.9, 0)] * 30 + [(0.1, 0)] * 30)
    newer = Calibrator.from_resolved([(0.9, 1)] * 30 + [(0.1, 1)] * 30)

    with paper_trade.get_bot_conn() as conn:
        save(conn, older)
        time.sleep(0.01)
        save(conn, newer)

    with paper_trade.get_bot_conn() as conn:
        loaded = load_latest(conn)

    assert loaded.predict(0.5) == pytest.approx(newer.predict(0.5), abs=1e-6)


# ---------------------------------------------------------------------------
# fit_and_save end-to-end against the real signals table
# ---------------------------------------------------------------------------


def test_fit_and_save_uses_resolved_signals():
    from calibration import fit_and_save, MIN_SAMPLES
    from paper_trade import log_signal, resolve_signal, get_conn, get_bot_conn

    # Log MIN_SAMPLES "0.95 says YES" trades, win 70% of them
    for i in range(MIN_SAMPLES):
        sid = log_signal({
            "market_id": f"m{i}", "question": f"q{i}", "direction": "YES",
            "price": 0.10, "edge": 0.20, "avg_prob": 0.95, "disagreement": 0.05,
        }, trade_size=10.0)
        resolve_signal(sid, "YES" if i < int(MIN_SAMPLES * 0.7) else "NO")

    iso = fit_and_save(get_conn, get_bot_conn)
    assert iso.is_identity is False
    assert iso.predict(0.95) == pytest.approx(0.70, abs=0.10)


def test_fit_and_save_below_threshold_returns_identity():
    from calibration import fit_and_save
    from paper_trade import log_signal, resolve_signal, get_conn, get_bot_conn

    # Only 5 resolved signals — under MIN_SAMPLES.
    for i in range(5):
        sid = log_signal({
            "market_id": f"m{i}", "question": f"q{i}", "direction": "YES",
            "price": 0.10, "edge": 0.20, "avg_prob": 0.95, "disagreement": 0.05,
        }, trade_size=10.0)
        resolve_signal(sid, "YES")

    iso = fit_and_save(get_conn, get_bot_conn)
    assert iso.is_identity is True


# ---------------------------------------------------------------------------
# Reliability diagram helper (used by `report`)
# ---------------------------------------------------------------------------


def test_tier2_uses_calibrator_to_compute_edge(monkeypatch):
    """The killer test: verify tier2_analyze applies the calibrator before edge.

    A market priced at 0.30 with raw consensus 0.95 currently fires (edge +0.65).
    Once we apply a calibrator that maps 0.95 -> 0.55, the same situation should
    yield edge +0.25 — still a trade — but if we calibrate to 0.40, edge becomes
    +0.10 < MIN_EDGE and the trade is skipped. We test both branches.
    """
    import asyncio
    import calibration as calmod
    from strategies import llm

    monkeypatch.setattr(llm, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(llm, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm, "XAI_AVAILABLE", True)
    monkeypatch.setattr(llm, "GOOGLE_AVAILABLE", False)
    monkeypatch.setattr(llm, "DEEPSEEK_AVAILABLE", False)

    async def fake_news(_q):
        return ""
    monkeypatch.setattr(llm, "fetch_news", fake_news)

    async def fake_claude(_q, _n): return 0.95
    async def fake_gpt(_q, _n):    return 0.95
    async def fake_grok(_q, _n):   return 0.95
    monkeypatch.setattr(llm, "call_claude", fake_claude)
    monkeypatch.setattr(llm, "call_gpt", fake_gpt)
    monkeypatch.setattr(llm, "call_grok", fake_grok)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "Will it rain tomorrow?",
        "yes_price": 0.30, "no_price": 0.70,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    # 1) identity calibrator -> trade fires with raw avg
    sig = asyncio.run(llm.tier2_analyze(market, calibrator=calmod.Calibrator.identity()))
    assert sig is not None
    assert sig["avg_prob"] == pytest.approx(0.95)
    assert sig["raw_prob"] == pytest.approx(0.95)
    assert sig["edge"] == pytest.approx(0.65, abs=0.01)

    # 2) calibrator that shrinks 0.95 -> 0.55 -> still a trade, smaller edge
    cal = calmod.Calibrator.from_resolved([(0.95, 1)] * 55 + [(0.95, 0)] * 45)
    assert cal.predict(0.95) == pytest.approx(0.55, abs=0.05)
    sig = asyncio.run(llm.tier2_analyze(market, calibrator=cal))
    assert sig is not None
    assert sig["avg_prob"] == pytest.approx(cal.predict(0.95), abs=1e-6)
    assert sig["raw_prob"] == pytest.approx(0.95)
    assert sig["edge"] < 0.30

    # 3) calibrator that shrinks 0.95 -> 0.40 -> edge < MIN_EDGE -> SKIP
    cal_strong = calmod.Calibrator.from_resolved([(0.95, 1)] * 40 + [(0.95, 0)] * 60)
    assert cal_strong.predict(0.95) == pytest.approx(0.40, abs=0.05)
    sig = asyncio.run(llm.tier2_analyze(market, calibrator=cal_strong))
    assert sig is None  # edge ~0.10 < MIN_EDGE 0.12


def test_reliability_diagram_buckets_and_counts():
    from calibration import reliability_diagram
    samples = [(0.05, 0)] * 10 + [(0.55, 1)] * 5 + [(0.55, 0)] * 5 + [(0.95, 1)] * 8 + [(0.95, 0)] * 2
    bins = reliability_diagram(samples, n_bins=10)
    # dict keyed by bin index 0..9
    assert bins[0]["n"] == 10
    assert bins[0]["accuracy"] == pytest.approx(0.0)
    assert bins[5]["n"] == 10
    assert bins[5]["accuracy"] == pytest.approx(0.5)
    assert bins[9]["n"] == 10
    assert bins[9]["accuracy"] == pytest.approx(0.8)
