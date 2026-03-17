import os
import json
import asyncio
from dotenv import load_dotenv

from pydantic import BaseModel

import anthropic
from openai import AsyncOpenAI
from google import genai

from tavily import AsyncTavilyClient

load_dotenv()

# --- Clients ---
claude         = anthropic.AsyncAnthropic()
openai_client  = AsyncOpenAI()
grok_client    = AsyncOpenAI(api_key=os.getenv("XAI_API_KEY"),      base_url="https://api.x.ai/v1")
deepseek_client = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
gemini         = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
tavily         = AsyncTavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# --- Config ---
MIN_EDGE         = 0.12   # 12% minimum — clears LLM error margin (~8-10% avg)
MAX_DISAGREEMENT = 0.15   # 15% max disagreement — filters noise, keeps tradeable signals
TIER1_PICK       = 5      # top 5 markets for deep analysis

async def fetch_news(question: str) -> str:
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
                f"- YES price 0.15–0.85 (genuine uncertainty)\n"
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
    "1. Consider the base rate — how often do events like this occur historically?\n"
    "2. Consider the strongest reasons this WILL happen (YES)\n"
    "3. Consider the strongest reasons this WON'T happen (NO)\n"
    "4. Weigh the evidence and give your honest probability for YES (0.0–1.0). "
    "Never return exactly 0.0 or 1.0 — there is always some uncertainty."
)

async def call_claude(question: str, news: str) -> float:
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


async def call_gpt(question: str, news: str) -> float:
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


async def call_gemini(question: str, news: str) -> float:
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

async def call_grok(question: str, news: str) -> float:
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


async def call_deepseek(question: str, news: str) -> float:
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

    claude_p, gpt_p, gemini_p, grok_p, deepseek_p = await asyncio.gather(
        call_claude(question, news),
        call_gpt(question, news),
        call_gemini(question, news),
        call_grok(question, news),
        call_deepseek(question, news),
    )

    probs        = [claude_p, gpt_p, gemini_p, grok_p, deepseek_p]
    trimmed      = sorted(probs)[1:-1]   # drop min and max, keep middle 3
    avg          = sum(trimmed) / len(trimmed)
    disagreement = max(probs) - min(probs)
    edge         = avg - yes_price

    print(f"\n{question[:60]}")
    print(f"  Claude={claude_p:.2f}  GPT={gpt_p:.2f}  Gemini={gemini_p:.2f}  Grok={grok_p:.2f}  DeepSeek={deepseek_p:.2f}")
    print(f"  avg={avg:.2f}  market={yes_price:.2f}  edge={edge:+.2f}  disagreement={disagreement:.2f}")

    if disagreement > MAX_DISAGREEMENT:
        print(f"  → SKIP (disagreement {disagreement:.2f} > {MAX_DISAGREEMENT})")
        return None

    if abs(edge) < MIN_EDGE:
        print(f"  → SKIP (edge {abs(edge):.2f} < {MIN_EDGE})")
        return None

    direction = "YES" if edge > 0 else "NO"
    print(f"  → TRADE {direction}  edge={edge:+.2f}")

    return {
        "market_id":     market.get("conditionId", market["id"]),
        "question":      question,
        "direction":     direction,
        "price":         yes_price if direction == "YES" else market["no_price"],
        "edge":          abs(edge),
        "avg_prob":      avg,
        "disagreement":  disagreement,
    }
