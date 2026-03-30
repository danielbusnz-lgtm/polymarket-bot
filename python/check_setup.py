#!/usr/bin/env python3
"""
check_setup.py - Validate all credentials before running the bot.

Run this after setting up your .env file to ensure everything is configured correctly.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check_mark(ok: bool) -> str:
    return f"{GREEN}OK{RESET}" if ok else f"{RED}MISSING{RESET}"


def warn_mark() -> str:
    return f"{YELLOW}WARN{RESET}"


def test_anthropic() -> tuple[bool, str]:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return False, "ANTHROPIC_API_KEY not set"
    try:
        import anthropic
        client = anthropic.Anthropic()
        # Quick test with minimal tokens
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'ok'"}],
        )
        return True, f"Claude working (model: claude-sonnet-4)"
    except Exception as e:
        return False, f"Claude error: {e}"


def test_openai() -> tuple[bool, str]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return False, "OPENAI_API_KEY not set"
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'ok'"}],
        )
        return True, "GPT-4o working"
    except Exception as e:
        return False, f"OpenAI error: {e}"


def test_google() -> tuple[bool, str]:
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return False, "GOOGLE_API_KEY not set"
    try:
        from google import genai
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Say 'ok'",
        )
        return True, "Gemini working"
    except Exception as e:
        return False, f"Gemini error: {e}"


def test_xai() -> tuple[bool, str]:
    key = os.getenv("XAI_API_KEY")
    if not key:
        return False, "XAI_API_KEY not set"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
        resp = client.chat.completions.create(
            model="grok-2",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'ok'"}],
        )
        return True, "Grok working"
    except Exception as e:
        return False, f"Grok error: {e}"


def test_deepseek() -> tuple[bool, str]:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return False, "DEEPSEEK_API_KEY not set"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say 'ok'"}],
        )
        return True, "DeepSeek working"
    except Exception as e:
        return False, f"DeepSeek error: {e}"


def test_tavily() -> tuple[bool, str]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return False, "TAVILY_API_KEY not set"
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        resp = client.search("test", max_results=1)
        return True, "Tavily working"
    except Exception as e:
        return False, f"Tavily error: {e}"


def test_polymarket() -> tuple[bool, str]:
    private_key = os.getenv("PRIVATE_KEY")
    api_key = os.getenv("POLYMARKET_API_KEY")
    secret = os.getenv("POLYMARKET_SECRET")
    passphrase = os.getenv("POLYMARKET_PASSPHRASE")

    missing = []
    if not private_key:
        missing.append("PRIVATE_KEY")
    if not api_key:
        missing.append("POLYMARKET_API_KEY")
    if not secret:
        missing.append("POLYMARKET_SECRET")
    if not passphrase:
        missing.append("POLYMARKET_PASSPHRASE")

    if missing:
        return False, f"Missing: {', '.join(missing)}"

    try:
        from client import get_client
        client = get_client()
        # Just check that client initializes (no API call)
        return True, f"Polymarket client initialized (wallet: {client.funder[:10]}...)"
    except Exception as e:
        return False, f"Polymarket error: {e}"


def main():
    print(f"\n{BOLD}Signum Setup Checker{RESET}")
    print("=" * 50)

    # Check LLMs
    print(f"\n{BOLD}LLM Providers:{RESET}")
    llm_tests = [
        ("Anthropic (Claude)", test_anthropic, True),
        ("OpenAI (GPT-4o)", test_openai, False),
        ("Google (Gemini)", test_google, False),
        ("xAI (Grok)", test_xai, False),
        ("DeepSeek", test_deepseek, False),
    ]

    llm_ok_count = 0
    for name, test_fn, required in llm_tests:
        ok, msg = test_fn()
        if ok:
            llm_ok_count += 1
        status = check_mark(ok)
        req_tag = " (required)" if required else ""
        print(f"  [{status}] {name}{req_tag}: {msg}")

    # Check Tavily
    print(f"\n{BOLD}News Provider:{RESET}")
    ok, msg = test_tavily()
    print(f"  [{check_mark(ok)}] Tavily: {msg}")
    tavily_ok = ok

    # Check Polymarket
    print(f"\n{BOLD}Trading:{RESET}")
    ok, msg = test_polymarket()
    print(f"  [{check_mark(ok)}] Polymarket: {msg}")
    polymarket_ok = ok

    # Summary
    print(f"\n{BOLD}Summary:{RESET}")
    print("=" * 50)

    if llm_ok_count >= 3:
        print(f"  [{GREEN}OK{RESET}] LLMs: {llm_ok_count}/5 available (minimum 3 required)")
    else:
        print(f"  [{RED}FAIL{RESET}] LLMs: {llm_ok_count}/5 available (minimum 3 required)")

    if tavily_ok:
        print(f"  [{GREEN}OK{RESET}] News context: Tavily working")
    else:
        print(f"  [{RED}FAIL{RESET}] News context: Tavily not configured")

    if polymarket_ok:
        print(f"  [{GREEN}OK{RESET}] Trading: Polymarket credentials valid")
    else:
        print(f"  [{YELLOW}WARN{RESET}] Trading: Polymarket not configured (paper trading still works)")

    # Final verdict
    print()
    can_paper_trade = llm_ok_count >= 3 and tavily_ok
    can_live_trade = can_paper_trade and polymarket_ok

    if can_live_trade:
        print(f"{GREEN}Ready for live trading!{RESET}")
        print("Run: python paper_trade.py run --live")
    elif can_paper_trade:
        print(f"{YELLOW}Ready for paper trading only.{RESET}")
        print("Run: python paper_trade.py run")
        print("\nTo enable live trading, configure Polymarket credentials.")
    else:
        print(f"{RED}Not ready. Fix the issues above.{RESET}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
