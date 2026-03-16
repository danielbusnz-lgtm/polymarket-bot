import os
import json
import asyncio
from dotenv import load_dotenv

from pydantic import BaseModel

import anthropic
from openai import AsyncOpenAI
from google import genai

from tavily import TavilyClient

load_dotenv()

# --- Clients ---
claude  = anthropic.AsyncAnthropic()
openai_client = AsyncOpenAI()
gemini  = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
tavily  = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# --- Config ---
MIN_EDGE         = 0.12   # 12% minimum — clears LLM error margin (~8-10% avg)
MAX_DISAGREEMENT = 0.10   # 10% max disagreement — tighter = higher signal quality
TIER1_PICK       = 5      # top 5 markets for deep analysis

async def fetch_news(question: str) -> str:
    def _search():
        results = tavily.search(
            query=question,
            search_depth="advanced",
            max_results=5,
            include_answer="advanced",
            exclude_domains=["youtube.com", "youtu.be"],
        )
        parts = []
        if results.get("answer"):
            parts.append(f"Summary: {results['answer']}\n")
        articles = results.get("results", [])
        for a in articles:
            parts.append(f"- {a['title']}: {a['content'][:500]}")
        return "\n".join(parts)

    return await asyncio.to_thread(_search)

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


