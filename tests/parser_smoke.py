"""Parser smoke test against varied Polymarket data.

Pulls markets from several different filter buckets (active, resolved,
newest, oldest, random offsets) and tries to parse each into a `Market`
dataclass. Reports parse failures and edge cases (non-binary outcomes,
prices outside [0,1], unparseable dates, missing fields).

Run this whenever the Market schema changes to catch real-world edge
cases before they crash production.
"""

import sys
from pathlib import Path

# Source modules live at the project root, one level up from tests/.
sys.path.insert(0, str(Path(__file__).parent.parent))

import random
import time
from collections import Counter

import httpx

from gamma import HOST
from market import Market


BUCKETS = [
    {
        "label": "top volume (active)",
        "params": {
            "active": "true", "closed": "false", "archived": "false",
            "order": "volume24hr", "ascending": "false", "limit": 25,
        },
    },
    {
        "label": "resolved markets",
        "params": {
            "closed": "true", "order": "volume", "ascending": "false", "limit": 25,
        },
    },
    {
        "label": "newest listed",
        "params": {
            "active": "true", "order": "createdAt", "ascending": "false", "limit": 25,
        },
    },
    {
        "label": "long-tail active (low volume)",
        "params": {
            "active": "true", "closed": "false",
            "order": "volume24hr", "ascending": "true", "limit": 25,
        },
    },
    {
        "label": "random offset 1",
        "params": {"limit": 25, "offset": str(random.randint(0, 5000))},
    },
    {
        "label": "random offset 2",
        "params": {"limit": 25, "offset": str(random.randint(5000, 15000))},
    },
]


def main() -> None:
    failures: list[tuple[str, str, str]] = []
    notes: list[str] = []
    outcome_counts: Counter[int] = Counter()
    total = 0
    parsed = 0

    for bucket in BUCKETS:
        print(f"\n=== {bucket['label']} ===")
        try:
            resp = httpx.get(f"{HOST}/markets", params=bucket["params"], timeout=20.0)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"  HTTP error: {e}")
            continue

        body = resp.json()
        if not isinstance(body, list):
            print(f"  unexpected body shape: {type(body).__name__}")
            continue
        print(f"  fetched {len(body)} markets")

        for raw in body:
            total += 1
            question = (raw.get("question") or "?")[:60]
            try:
                m = Market.from_gamma(raw)
            except Exception as e:
                failures.append((question, type(e).__name__, str(e)))
                continue
            parsed += 1
            outcome_counts[len(m.outcomes)] += 1

            if len(m.outcomes) != len(m.outcome_prices):
                notes.append(
                    f"outcomes/prices length mismatch ({len(m.outcomes)} vs "
                    f"{len(m.outcome_prices)}): {question}"
                )
            if m.outcome_prices and (
                max(m.outcome_prices) > 1.0 or min(m.outcome_prices) < 0.0
            ):
                notes.append(
                    f"price out of [0,1]: {m.outcome_prices} -- {question}"
                )
            if m.end_date is None and raw.get("endDate"):
                notes.append(
                    f"endDate parse failed ({raw.get('endDate')!r}) -- {question}"
                )
            if not m.clob_token_ids:
                notes.append(f"no clob_token_ids -- {question}")
            if m.neg_risk:
                notes.append(f"neg_risk market -- {question}")

        time.sleep(0.3)  # polite pacing

    print("\n\n=== summary ===")
    print(f"total markets seen : {total}")
    print(f"parsed cleanly     : {parsed}")
    print(f"parse failures     : {len(failures)}")
    print(f"outcome counts     : {dict(outcome_counts)}")
    print(f"misc notes         : {len(notes)}")

    if failures:
        print("\nFailures:")
        for q, errtype, errmsg in failures:
            print(f"  [{errtype}] {q}")
            print(f"      {errmsg}")

    if notes:
        print("\nNotes (first 20):")
        for n in notes[:20]:
            print(f"  {n}")


if __name__ == "__main__":
    main()
