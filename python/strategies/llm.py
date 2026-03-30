import os
import json
import asyncio
from dotenv import load_dotenv

from pydantic import BaseModel

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


async def tier2_analyze(market: dict) -> dict | None:
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
    avg          = sum(trimmed) / len(trimmed)
    disagreement = max(probs) - min(probs)
    edge         = avg - yes_price

    print(f"\n{question[:60]}")
    parts = []
    for name, r in zip(model_names, results):
        parts.append(f"{name}={r:.2f}" if r is not None else f"{name}=FAIL")
    print(f"  {' '.join(parts)}")
    print(f"  avg={avg:.2f}  market={yes_price:.2f}  edge={edge:+.2f}  disagreement={disagreement:.2f}")

    if disagreement > MAX_DISAGREEMENT:
        print(f"  -> SKIP (disagreement {disagreement:.2f} > {MAX_DISAGREEMENT})")
        return None

    if abs(edge) < MIN_EDGE:
        print(f"  -> SKIP (edge {abs(edge):.2f} < {MIN_EDGE})")
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
        "disagreement":  disagreement,
    }
