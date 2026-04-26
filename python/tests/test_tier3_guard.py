"""Tier 3: short-deadline event guard.

Hard-veto trades that match the catastrophic loss zone: high model confidence
(>=0.85) + low market price (<0.30) + question phrased as 'by [date]' + no
news evidence of a concrete scheduled event. This is the rule that would have
killed both Iran-meeting trades from week of 2026-04-24 with no training data
required.
"""

import os
import sys
import asyncio
import tempfile

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
# Question detector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("question, expected", [
    ("US x Iran diplomatic meeting by April 25, 2026?",      True),
    ("US x Iran diplomatic meeting by April 27, 2026?",      True),
    ("Will the Fed cut rates by July 2026?",                 True),
    ("Will Trump pardon Hunter Biden by end of June?",       True),
    ("Will the BJP win the most seats in 2028 election?",    False),
    ("Will Bitcoin reach $100k?",                            False),
    ("Will the Fed cut rates?",                              False),
    ("Who will win the 2028 election?",                      False),
])
def test_is_short_deadline_event_question(question, expected):
    from strategies.llm import is_short_deadline_event_question
    assert is_short_deadline_event_question(question) is expected


# ---------------------------------------------------------------------------
# Integration: guard inside tier2_analyze
# ---------------------------------------------------------------------------


def _wire_three_models(monkeypatch, prob: float = 0.95):
    from strategies import llm
    monkeypatch.setattr(llm, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(llm, "OPENAI_AVAILABLE",   True)
    monkeypatch.setattr(llm, "XAI_AVAILABLE",      True)
    monkeypatch.setattr(llm, "GOOGLE_AVAILABLE",   False)
    monkeypatch.setattr(llm, "DEEPSEEK_AVAILABLE", False)

    async def fake_news(_q): return ""
    monkeypatch.setattr(llm, "fetch_news", fake_news)

    async def fake_call(_q, _n): return prob
    monkeypatch.setattr(llm, "call_claude", fake_call)
    monkeypatch.setattr(llm, "call_gpt",    fake_call)
    monkeypatch.setattr(llm, "call_grok",   fake_call)


def test_iran_trade_pattern_skipped_when_no_scheduled_event(monkeypatch):
    """Reproduces last week's failure exactly — the guard must kill it."""
    from strategies import llm

    _wire_three_models(monkeypatch, prob=0.95)

    async def no_event(_q, _n): return False
    monkeypatch.setattr(llm, "has_scheduled_event_in_news", no_event)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "US x Iran diplomatic meeting by April 25, 2026?",
        "yes_price": 0.06, "no_price": 0.94,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    sig = asyncio.run(llm.tier2_analyze(market))
    assert sig is None, "Tier 3 guard should have killed this trade"


def test_short_deadline_trade_passes_when_news_confirms_scheduled_event(monkeypatch):
    """If Tavily found 'meeting confirmed for April 25 at 2pm GMT', let it through."""
    from strategies import llm

    _wire_three_models(monkeypatch, prob=0.95)

    async def has_event(_q, _n): return True
    monkeypatch.setattr(llm, "has_scheduled_event_in_news", has_event)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "US x Iran diplomatic meeting by April 25, 2026?",
        "yes_price": 0.06, "no_price": 0.94,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    sig = asyncio.run(llm.tier2_analyze(market))
    assert sig is not None
    assert sig["direction"] == "YES"


def test_guard_does_not_apply_to_non_event_question(monkeypatch):
    """Election market shouldn't trigger the guard even at high confidence + low price."""
    from strategies import llm

    _wire_three_models(monkeypatch, prob=0.95)

    # Wire a no-scheduled-event response — the guard mustn't reach this anyway
    async def no_event(_q, _n):
        raise AssertionError("guard should not have called the news classifier")
    monkeypatch.setattr(llm, "has_scheduled_event_in_news", no_event)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "Will Trump win the 2028 election?",
        "yes_price": 0.10, "no_price": 0.90,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    sig = asyncio.run(llm.tier2_analyze(market))
    assert sig is not None  # election questions skip the guard


def test_guard_does_not_apply_when_market_already_priced_high(monkeypatch):
    """When market_price >= 0.30, the guard is off — only catastrophic-zone trades trigger it."""
    from strategies import llm

    _wire_three_models(monkeypatch, prob=0.95)

    async def no_event(_q, _n):
        raise AssertionError("guard should not have called the news classifier")
    monkeypatch.setattr(llm, "has_scheduled_event_in_news", no_event)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "Will the ceasefire be signed by May 15, 2026?",
        "yes_price": 0.45, "no_price": 0.55,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    sig = asyncio.run(llm.tier2_analyze(market))
    assert sig is not None


def test_guard_does_not_apply_when_consensus_below_threshold(monkeypatch):
    """At raw consensus < 0.85, the guard is off."""
    from strategies import llm

    _wire_three_models(monkeypatch, prob=0.65)

    async def no_event(_q, _n):
        raise AssertionError("guard should not have called the news classifier")
    monkeypatch.setattr(llm, "has_scheduled_event_in_news", no_event)

    market = {
        "id": "m1", "conditionId": "c1",
        "question": "US x Iran diplomatic meeting by April 25, 2026?",
        "yes_price": 0.06, "no_price": 0.94,
        "yes_token_id": "yt", "no_token_id": "nt",
    }

    sig = asyncio.run(llm.tier2_analyze(market))
    assert sig is not None  # raw 0.65 -> no guard, normal edge filter applies


# ---------------------------------------------------------------------------
# MIN_SAMPLES lowered
# ---------------------------------------------------------------------------


def test_min_samples_threshold_lowered():
    from calibration import MIN_SAMPLES
    assert MIN_SAMPLES == 10


# ---------------------------------------------------------------------------
# Defense-in-depth: a True from Claude isn't enough on its own
# ---------------------------------------------------------------------------


def _confirmation(confirmed: bool, quote: str = "", date: str = "", reasoning: str = ""):
    from strategies.llm import _ScheduleConfirmation
    return _ScheduleConfirmation(
        confirmed=confirmed, evidence_quote=quote, event_date=date, reasoning=reasoning,
    )


def test_is_confirmed_requires_quote_and_date():
    from strategies.llm import _is_confirmed
    # Claude says yes but provides no evidence -> not confirmed
    assert _is_confirmed(_confirmation(True, quote="", date="May 5")) is False
    assert _is_confirmed(_confirmation(True, quote="meeting set", date="")) is False
    assert _is_confirmed(_confirmation(True, quote="   ", date="May 5")) is False
    # Claude says yes with quote and date -> confirmed
    assert _is_confirmed(_confirmation(True, quote="meeting set for May 5",
                                       date="May 5, 2026")) is True
    # Claude says no -> never confirmed
    assert _is_confirmed(_confirmation(False, quote="meeting set",
                                       date="May 5, 2026")) is False


def test_no_news_returns_false_without_calling_claude(monkeypatch):
    """If Tavily failed and news is empty, the guard MUST fail closed."""
    import asyncio
    from strategies import llm

    sentinel = {"called": False}
    async def boom(*_a, **_kw):
        sentinel["called"] = True
        raise AssertionError("Claude should not be called when news is empty")

    monkeypatch.setattr(llm, "claude", type("C", (), {"messages": type("M", (), {"parse": boom})()})())
    result = asyncio.run(llm.has_scheduled_event_in_news("test?", ""))
    assert result is False
    assert sentinel["called"] is False
