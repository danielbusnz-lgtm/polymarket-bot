"""Claude-based market analyst with extended thinking + web search.

Given a Polymarket `Market`, asks Claude Opus 4.7 to do deep research on
the question (multiple web searches across angles) and reason carefully
(extended thinking budget) before committing to a probability.

Returns a `Prediction` object with both the float estimate and Claude's
final reasoning text. The internal "thinking" tokens are NOT exposed —
they're Claude's scratch space and don't need to be persisted.

Latency: 30-90s per call. Cost: ~$0.50-1.50 per prediction. Quality is
what we're optimizing for; everything else is secondary.
"""

import os
import re
from dataclasses import dataclass

from anthropic import Anthropic
from dotenv import load_dotenv

from market import Market

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192             # generous; thinking + reasoning + final answer
THINKING_EFFORT = "medium"    # 'low' | 'medium' | 'high'
MAX_SEARCHES = 5              # how many web_search calls Claude may make


WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": MAX_SEARCHES,
}


SYSTEM_PROMPT = """\
You are a senior prediction-market analyst. Your job is to estimate the true
probability that a Polymarket question resolves "Yes" by its deadline.

You have web_search available with up to 10 searches. You also have an
internal reasoning budget (extended thinking). USE BOTH AGGRESSIVELY. There
is no time pressure — taking 60 seconds to produce a well-calibrated answer
is far better than taking 5 seconds to produce a guess.

RESEARCH PROTOCOL — follow this every time:

1. RECENT DIRECT SIGNALS
   Search for the most recent news, official statements, public commitments,
   leaks, or scheduled events directly relevant to the question's deadline.
   Prefer primary sources (company press releases, named individual quotes,
   official filings) over speculation.

2. HISTORICAL BASE RATE
   Search for how often similar events have hit their stated deadlines.
   Companies miss launch deadlines; legislative bodies miss vote deadlines;
   product schedules slip. Establish the base rate before adjusting.

3. SPECIFIC CATALYSTS AND BLOCKERS
   What concrete events between now and the deadline would push the
   probability up? Down? Search for evidence each is or isn't on track.

4. CROSS-REFERENCE
   Don't rely on a single article. Independent confirmation matters. If
   only one source mentions something, weight it less.

5. COUNTER-CRITIQUE
   Before finalizing: "What would make me wrong?" Search for the
   strongest argument against your current estimate. Update accordingly.

6. CALIBRATE — DON'T ANCHOR
   You will see the current market price. DO NOT anchor on it. Form your
   own estimate first. THEN, if your estimate is wildly different from the
   market, ask why — what does the market know that you don't? Sometimes
   markets are wrong. Sometimes you are.

SOURCE QUALITY HEURISTICS:
- Trust: SEC filings, official company announcements, statements from named
  decision-makers, multiple independent confirmations
- Distrust: social media rumors without corroboration, anonymous "leaks",
  hype/speculation pieces, sources with vested interests (bag-holders,
  marketers)

OUTPUT FORMAT:

After your reasoning, finish with sections in EXACTLY this format:

KEY FACTS:
- (3-5 bullet points, each with a source if possible)

BASE RATE: <one sentence>

KEY UNCERTAINTIES:
- (2-3 things that could swing the estimate)

PROBABILITY: <decimal between 0 and 1>
CONFIDENCE: <HIGH | MEDIUM | LOW>
"""


@dataclass
class Prediction:
    probability: float
    confidence: str            # 'HIGH', 'MEDIUM', 'LOW', or 'UNKNOWN'
    reasoning: str             # full Claude text (excluding internal thinking)
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    web_searches: int
    cost_usd: float            # computed from tokens + per-model pricing


# Per-million-tokens, USD. Update when Anthropic changes pricing. Cache write
# = input × 1.25, cache read = input × 0.10 (Anthropic's standard ratios).
PRICING_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0, "cw": 18.75, "cr": 1.50},
    "claude-sonnet-4-6": {"input":  3.0, "output": 15.0, "cw":  3.75, "cr": 0.30},
    "claude-haiku-4-5":  {"input":  1.0, "output":  5.0, "cw":  1.25, "cr": 0.10},
}
WEB_SEARCH_USD_PER_REQUEST = 0.010    # $10 / 1k searches


_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def predict(market: Market) -> Prediction:
    """Deep research + extended-thinking prediction for one market."""
    user_msg = (
        f"Market: {market.question}\n"
        f"Description: {market.description or '(none)'}\n"
        f"Resolves: {market.end_date.isoformat() if market.end_date else 'unknown'}\n"
        f"Outcomes: {market.outcomes}\n"
        f"\n"
        f"Current market state (do not anchor on this; form your own view first):\n"
        f"  Yes price:    {market.outcome_prices[0]:.4f} "
        f"({market.outcome_prices[0] * 100:.1f}%)\n"
        f"  Volume 24h:   ${market.volume_24hr:,.0f}\n"
        f"  Liquidity:    ${market.liquidity:,.0f}\n"
        f"\n"
        f"Do thorough research, then give your estimate."
    )

    client = _get_client()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": THINKING_EFFORT},
        system=SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": user_msg}],
    )

    # Claude returns a mix of block types. We surface the user-facing TEXT
    # blocks only; thinking blocks are Claude's internal scratch and are
    # deliberately not persisted.
    text_parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    full_text = "\n".join(text_parts).strip()

    usage = resp.usage
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    server_use = getattr(usage, "server_tool_use", None)
    web_searches = getattr(server_use, "web_search_requests", 0) if server_use else 0

    cost = _compute_cost(
        model=MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read=cache_read,
        cache_write=cache_write,
        web_searches=web_searches,
    )

    return Prediction(
        probability=_extract_prob(full_text),
        confidence=_extract_confidence(full_text),
        reasoning=full_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        web_searches=web_searches,
        cost_usd=cost,
    )


def _compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write: int,
    web_searches: int,
) -> float:
    rates = PRICING_PER_MILLION.get(model)
    if rates is None:
        return 0.0    # unknown model; log zero rather than crash
    return (
        (input_tokens  * rates["input"]  / 1_000_000)
        + (output_tokens * rates["output"] / 1_000_000)
        + (cache_read    * rates["cr"]     / 1_000_000)
        + (cache_write   * rates["cw"]     / 1_000_000)
        + (web_searches  * WEB_SEARCH_USD_PER_REQUEST)
    )


def _extract_prob(text: str) -> float:
    """Find the 'PROBABILITY: <num>' line. Fall back to the last decimal."""
    m = re.search(r"PROBABILITY:\s*([\d.]+)", text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
    else:
        nums = re.findall(r"[-+]?\d*\.?\d+", text)
        if not nums:
            raise ValueError(f"no number in claude response: {text!r}")
        val = float(nums[-1])
    if val > 1.0:
        val = val / 100
    return max(0.0, min(1.0, val))


def _extract_confidence(text: str) -> str:
    m = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    return m.group(1).upper() if m else "UNKNOWN"


PROMPT_VERSION = "v2-deep-research"


def main() -> None:
    """Pick one filtered candidate, run deep research, persist to ledger."""
    from filters import fetch_and_screen
    import repo

    candidates = fetch_and_screen()
    if not candidates:
        print("no candidates passed the filter pipeline")
        return

    market = max(candidates, key=lambda m: m.volume_24hr)
    yes_price = market.outcome_prices[0]
    print(f"=== {market.question} ===\n")
    print(f"market 'Yes' : {yes_price:.4f}  ({yes_price * 100:.2f}%)")
    print(f"resolves     : {market.end_date}\n")
    print(f"running deep research (model={MODEL}, thinking={THINKING_EFFORT}, "
          f"max searches={MAX_SEARCHES})...")
    print("this may take 30-90s.\n")

    pred = predict(market)

    # Persist the full chain: market metadata → snapshot of state at predict
    # time → the prediction itself with FULL reasoning text.
    repo.upsert_market(market)
    snap_id = repo.record_snapshot(market)
    pred_id = repo.record_prediction(
        market_id=market.id,
        snapshot_id=snap_id,
        yes_probability=pred.probability,
        model=MODEL,
        prompt_version=PROMPT_VERSION,
        confidence=pred.confidence,
        raw_response=pred.reasoning,
        input_tokens=pred.input_tokens,
        output_tokens=pred.output_tokens,
        cache_read_tokens=pred.cache_read_tokens,
        cache_write_tokens=pred.cache_write_tokens,
        web_searches=pred.web_searches,
        cost_usd=pred.cost_usd,
    )

    print("=== claude reasoning ===\n")
    print(pred.reasoning)
    print()
    print(f"=== verdict ===")
    print(f"claude probability : {pred.probability:.4f}  "
          f"({pred.probability * 100:.2f}%)")
    print(f"confidence         : {pred.confidence}")
    print(f"divergence vs mkt  : {pred.probability - yes_price:+.4f}  "
          f"({(pred.probability - yes_price) * 100:+.2f}pp)")
    print()
    print(f"=== this call ===")
    print(f"input tokens     : {pred.input_tokens:,}")
    print(f"output tokens    : {pred.output_tokens:,}")
    if pred.cache_read_tokens or pred.cache_write_tokens:
        print(f"cache (read/write) : {pred.cache_read_tokens:,} / {pred.cache_write_tokens:,}")
    print(f"web searches     : {pred.web_searches}")
    print(f"cost             : ${pred.cost_usd:.4f}")
    print()
    print(f"=== persisted ===")
    print(f"market           : {market.id} (upserted)")
    print(f"snapshot         : #{snap_id}")
    print(f"prediction       : #{pred_id} ({len(pred.reasoning):,} chars of reasoning)")
    print()
    summary = repo.cost_summary()
    print(f"=== running ai cost ===")
    print(f"predictions made : {summary['n_predictions']}")
    print(f"total cost       : ${summary['total_cost_usd']:.4f}")
    print(f"total tokens     : {summary['total_input_tokens']:,} in / "
          f"{summary['total_output_tokens']:,} out")
    print(f"total searches   : {summary['total_web_searches']}")
    for row in summary['per_model']:
        print(f"  {row['model']:<22}  {row['n']:>3} calls  ${row['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
