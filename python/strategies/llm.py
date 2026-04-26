import os
import re
import json
import asyncio
from dotenv import load_dotenv

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

# Retry transient errors (429s, timeouts, 5xx) up to 3 times.
# Auth errors will exhaust retries cheaply — safe_call swallows the final raise.
_llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)

load_dotenv()

# --- Check which providers are available ---
ANTHROPIC_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
OPENAI_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
GOOGLE_AVAILABLE = bool(os.getenv("GOOGLE_API_KEY"))
XAI_AVAILABLE = bool(os.getenv("XAI_API_KEY"))
DEEPSEEK_AVAILABLE = bool(os.getenv("DEEPSEEK_API_KEY"))
TAVILY_AVAILABLE = bool(os.getenv("TAVILY_API_KEY"))

# Count available LLMs
_available_llms = sum([
    ANTHROPIC_AVAILABLE,
    OPENAI_AVAILABLE,
    GOOGLE_AVAILABLE,
    XAI_AVAILABLE,
    DEEPSEEK_AVAILABLE,
])

# --- Initialize only available clients ---
claude = None
openai_client = None
grok_client = None
deepseek_client = None
gemini = None
tavily = None

if ANTHROPIC_AVAILABLE:
    import anthropic
    claude = anthropic.AsyncAnthropic()

if OPENAI_AVAILABLE:
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI()

if XAI_AVAILABLE:
    from openai import AsyncOpenAI as AsyncOpenAI_XAI
    grok_client = AsyncOpenAI_XAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1")

if DEEPSEEK_AVAILABLE:
    from openai import AsyncOpenAI as AsyncOpenAI_DS
    deepseek_client = AsyncOpenAI_DS(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

if GOOGLE_AVAILABLE:
    from google import genai
    gemini = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

if TAVILY_AVAILABLE:
    from tavily import AsyncTavilyClient
    tavily = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# --- Config ---
MIN_EDGE         = 0.12   # 12% minimum - clears LLM error margin (~8-10% avg)
MAX_DISAGREEMENT = 0.15   # 15% max disagreement - filters noise, keeps tradeable signals
TIER1_PICK       = 5      # top 5 markets for deep analysis
MIN_LLMS         = 3      # minimum LLMs needed for consensus

# Tier 3 guard thresholds — only veto the catastrophic-zone trades.
GUARD_RAW_PROB   = 0.85   # raw consensus must be >=0.85 to trip the guard
GUARD_MAX_PRICE  = 0.30   # market YES price must be <0.30 to trip the guard

# Matches "by [Month Day]"/"by [Month Day, Year]"/"by 5/3/26"/"by end of [period]".
_SHORT_DEADLINE_RE = re.compile(
    r"\b(?:by|before)\s+("
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:,?\s*\d{2,4})?"
    r"|\d{1,2}[\/\-]\d{1,2}(?:[\/\-]\d{2,4})?"
    r"|end\s+of\s+\w+"
    r")\b",
    re.IGNORECASE,
)


def is_short_deadline_event_question(question: str) -> bool:
    """Detects 'will X happen by [date]' phrasing — the failure pattern that
    bit us on Iran-meeting markets. Long-form election/policy questions
    don't match."""
    return bool(_SHORT_DEADLINE_RE.search(question or ""))


class _ScheduleConfirmation(BaseModel):
    confirmed: bool
    reasoning: str


async def has_scheduled_event_in_news(question: str, news: str) -> bool:
    """Returns True only if the news context contains a *concrete, scheduled*
    event with a specific date/time that would resolve the question YES.

    Speculation, diplomatic talks-about-talks, or 'sources say' don't count.
    Conservative on no-info: returns False if news is empty or Claude is
    unavailable, which means the guard fails closed (skips the trade)."""
    if not claude or not news.strip():
        return False
    response = await claude.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"News context:\n{news}\n\n"
                f"Is there a *concrete, publicly announced, scheduled* event with "
                f"a specific date that would directly resolve this question YES "
                f"before its deadline? Speculation, ongoing talks, leaks, or "
                f"'expected to happen' do NOT count — only a confirmed scheduled "
                f"event does. Answer strictly true or false."
            ),
        }],
        output_format=_ScheduleConfirmation,
    )
    return response.parsed_output.confirmed


def print_provider_status():
    """Print which providers are available at startup."""
    providers = [
        ("Anthropic (Claude)", ANTHROPIC_AVAILABLE, True),
        ("OpenAI (GPT-4o)", OPENAI_AVAILABLE, False),
        ("Google (Gemini)", GOOGLE_AVAILABLE, False),
        ("xAI (Grok)", XAI_AVAILABLE, False),
        ("DeepSeek", DEEPSEEK_AVAILABLE, False),
        ("Tavily (news)", TAVILY_AVAILABLE, True),
    ]

    print("\nLLM Providers:")
    for name, available, required in providers:
        status = "OK" if available else ("MISSING (required)" if required else "MISSING (optional)")
        print(f"  {name}: {status}")

    print(f"\nAvailable LLMs: {_available_llms}/5 (minimum {MIN_LLMS} required)")

    if _available_llms < MIN_LLMS:
        raise RuntimeError(f"Need at least {MIN_LLMS} LLM providers. Only {_available_llms} configured.")

    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("Anthropic API key required (used for Tier 1 screening).")

    if not TAVILY_AVAILABLE:
        raise RuntimeError("Tavily API key required (used for news context).")


async def fetch_news(question: str) -> str:
    if not tavily:
        return "(no news context - Tavily not configured)"

    results = await tavily.search(
        query=question,
        search_depth="advanced",
        chunks_per_source=3,
        max_results=8,
        topic="news",
        time_range="month",
        include_answer="advanced",
        exclude_domains=["youtube.com", "youtu.be"],
    )
    parts = []
    if results.get("answer"):
        parts.append(f"Summary: {results['answer']}\n")
    for a in results.get("results", []):
        if a.get("score", 0) < 0.5:
            continue
        parts.append(f"- {a['title']}: {a['content']}")
    return "\n".join(parts)


class FilterResult(BaseModel):
    keep: list[int]


async def filter_politics(candidates: list[dict]) -> list[dict]:
    if not claude:
        raise RuntimeError("Claude required for filter_politics")

    market_list = "\n".join([
        f"{i+1}. {m['question']}"
        for i, m in enumerate(candidates)
    ])

    response = await claude.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"Filter these prediction markets. Keep only:\n"
                f"- Politics (elections, policy, government actions)\n"
                f"- World events (wars, diplomacy, geopolitics)\n"
                f"- Major figures and their decisions\n\n"
                f"Remove:\n"
                f"- Commodities or financial instruments (oil, gold, stocks)\n"
                f"- Cryptocurrency prices\n"
                f"- Social media activity (tweet/post counts)\n"
                f"- Sports statistics\n\n"
                f"Markets:\n{market_list}\n\n"
                f"Return the numbers of markets to KEEP."
            ),
        }],
        output_format=FilterResult,
    )

    keep = response.parsed_output.keep
    return [candidates[i - 1] for i in keep if 1 <= i <= len(candidates)]


class ScreenResult(BaseModel):
    picks: list[int]


async def tier1_screen(candidates: list[dict]) -> list[dict]:
    if not claude:
        raise RuntimeError("Claude required for tier1_screen")

    market_list = "\n".join([
        f"{i+1}. [YES={m['yes_price']:.2f}] {m['question']}"
        for i, m in enumerate(candidates)
    ])

    response = await claude.messages.parse(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"You are screening prediction markets for mispricing opportunities.\n\n"
                f"Markets:\n{market_list}\n\n"
                f"Pick the {TIER1_PICK} most likely to be mispriced. Favour:\n"
                f"- YES price 0.15-0.85 (genuine uncertainty)\n"
                f"- Political/world events resolving within 2 weeks\n"
                f"- Markets where a careful reasoner could beat the crowd\n\n"
                f"Return only the numbers of your {TIER1_PICK} picks."
            ),
        }],
        output_format=ScreenResult,
    )

    picks = response.parsed_output.picks
    return [candidates[i - 1] for i in picks if 1 <= i <= len(candidates)]


class ProbResult(BaseModel):
    probability: float
    reasoning: str


SUPERFORECASTER_PROMPT = (
    "You are a superforecaster with a strong track record of accurate predictions. "
    "You carefully evaluate evidence and aim to predict future events as accurately as possible.\n\n"
    "Question: {question}\n\n"
    "Recent news:\n{news}\n\n"
    "Reason step by step:\n"
    "1. Consider the base rate - how often do events like this occur historically?\n"
    "2. Consider the strongest reasons this WILL happen (YES)\n"
    "3. Consider the strongest reasons this WON'T happen (NO)\n"
    "4. Weigh the evidence and give your honest probability for YES (0.0-1.0). "
    "Never return exactly 0.0 or 1.0 - there is always some uncertainty."
)


@_llm_retry
async def call_claude(question: str, news: str) -> float | None:
    if not claude:
        return None
    response = await claude.messages.parse(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": SUPERFORECASTER_PROMPT.format(question=question, news=news),
        }],
        output_format=ProbResult,
    )
    return response.parsed_output.probability


@_llm_retry
async def call_gpt(question: str, news: str) -> float | None:
    if not openai_client:
        return None
    response = await openai_client.chat.completions.parse(
        model="gpt-4o",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": SUPERFORECASTER_PROMPT.format(question=question, news=news),
        }],
        response_format=ProbResult,
    )
    return response.choices[0].message.parsed.probability


@_llm_retry
async def call_gemini(question: str, news: str) -> float | None:
    if not gemini:
        return None
    def _call():
        response = gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=SUPERFORECASTER_PROMPT.format(question=question, news=news),
            config={
                "response_mime_type": "application/json",
                "response_json_schema": ProbResult.model_json_schema(),
            },
        )
        return ProbResult.model_validate_json(response.text).probability
    return await asyncio.to_thread(_call)


@_llm_retry
async def call_grok(question: str, news: str) -> float | None:
    if not grok_client:
        return None
    response = await grok_client.chat.completions.parse(
        model="grok-3",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": SUPERFORECASTER_PROMPT.format(question=question, news=news),
        }],
        response_format=ProbResult,
    )
    return response.choices[0].message.parsed.probability


@_llm_retry
async def call_deepseek(question: str, news: str) -> float | None:
    if not deepseek_client:
        return None
    response = await deepseek_client.chat.completions.create(
        model="deepseek-reasoner",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": (
                SUPERFORECASTER_PROMPT.format(question=question, news=news) +
                '\n\nRespond with only a JSON object in this format: {"probability": 0.0, "reasoning": "..."}'
            ),
        }],
    )
    text = response.choices[0].message.content
    # extract JSON from response
    start = text.find("{")
    end   = text.rfind("}") + 1
    return ProbResult.model_validate_json(text[start:end]).probability


async def tier2_analyze(market: dict, calibrator=None) -> dict | None:
    question  = market["question"]
    yes_price = market["yes_price"]

    news = await fetch_news(question)

    async def safe_call(name: str, coro):
        try:
            result = await coro
            if result is None:
                return None  # Provider not configured
            return result
        except Exception as e:
            print(f"  [WARN] {name} failed: {e}")
            return None

    # Build list of calls - only for configured providers
    calls = []
    model_names = []

    if ANTHROPIC_AVAILABLE:
        calls.append(safe_call("Claude", call_claude(question, news)))
        model_names.append("Claude")

    if OPENAI_AVAILABLE:
        calls.append(safe_call("GPT", call_gpt(question, news)))
        model_names.append("GPT")

    if GOOGLE_AVAILABLE:
        calls.append(safe_call("Gemini", call_gemini(question, news)))
        model_names.append("Gemini")

    if XAI_AVAILABLE:
        calls.append(safe_call("Grok", call_grok(question, news)))
        model_names.append("Grok")

    if DEEPSEEK_AVAILABLE:
        calls.append(safe_call("DeepSeek", call_deepseek(question, news)))
        model_names.append("DeepSeek")

    results = await asyncio.gather(*calls)
    probs = [r for r in results if r is not None]

    if len(probs) < MIN_LLMS:
        print(f"\n{question[:60]}")
        print(f"  -> SKIP (only {len(probs)}/{len(calls)} models returned, need at least {MIN_LLMS})")
        return None

    trimmed      = sorted(probs)[1:-1] if len(probs) >= 5 else probs  # trim only if we have 5
    raw_avg      = sum(trimmed) / len(trimmed)
    avg          = calibrator.predict(raw_avg) if calibrator is not None else raw_avg
    disagreement = max(probs) - min(probs)
    edge         = avg - yes_price

    print(f"\n{question[:60]}")
    parts = []
    for name, r in zip(model_names, results):
        parts.append(f"{name}={r:.2f}" if r is not None else f"{name}=FAIL")
    print(f"  {' '.join(parts)}")
    if calibrator is not None and not getattr(calibrator, "is_identity", True):
        print(f"  raw={raw_avg:.2f}  calibrated={avg:.2f}  market={yes_price:.2f}  edge={edge:+.2f}  disagreement={disagreement:.2f}")
    else:
        print(f"  avg={avg:.2f}  market={yes_price:.2f}  edge={edge:+.2f}  disagreement={disagreement:.2f}")

    if disagreement > MAX_DISAGREEMENT:
        print(f"  -> SKIP (disagreement {disagreement:.2f} > {MAX_DISAGREEMENT})")
        return None

    if abs(edge) < MIN_EDGE:
        print(f"  -> SKIP (edge {abs(edge):.2f} < {MIN_EDGE})")
        return None

    # Tier 3: veto catastrophic-zone trades on short-deadline event markets
    # unless news contains a concrete scheduled event. This is the failure
    # mode that lost both Iran-meeting trades on 2026-04-24.
    if (raw_avg >= GUARD_RAW_PROB
            and yes_price < GUARD_MAX_PRICE
            and is_short_deadline_event_question(question)):
        confirmed = await has_scheduled_event_in_news(question, news)
        if not confirmed:
            print(f"  -> SKIP (short-deadline event with no scheduled-event "
                  f"confirmation in news context)")
            return None

    direction = "YES" if edge > 0 else "NO"
    print(f"  -> TRADE {direction}  edge={edge:+.2f}")

    token_id = market["yes_token_id"] if direction == "YES" else market["no_token_id"]

    return {
        "market_id":     market.get("conditionId", market["id"]),
        "question":      question,
        "direction":     direction,
        "token_id":      token_id,
        "price":         yes_price if direction == "YES" else market["no_price"],
        "edge":          abs(edge),
        "avg_prob":      avg,
        "raw_prob":      raw_avg,
        "disagreement":  disagreement,
    }
