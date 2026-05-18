"""Filter Polymarket markets down to candidates Claude has a chance with.

Targets the "Will [scheduled public event] happen by [date]?" niche where:
  - The deadline is public and reasoning-friendly (product launches, IPOs,
    bill passages, scheduled releases).
  - Markets are less institutionally efficient than politics or crypto.
  - Resolution is fast enough for a useful paper-trading feedback loop.

Filtering combines TWO stages:

1. **Tag filter** at Gamma fetch time. We only pull markets tagged Tech /
   AI / Business / Culture — categories where "by date" questions cluster.
2. **Python-side regex + meta filter** to reject markets that survive the
   tag filter but still aren't a fit (price-target questions, compound
   questions, illiquid markets, extreme prices, wrong time horizon).

`screen(markets)` is the main entry point.
"""

import re
from datetime import datetime, timedelta, timezone

from market import Market


# Gamma `tag_id` values for the categories Option 2 markets cluster in.
# Discovered empirically from the /events endpoint; see git log.
SCHEDULED_EVENT_TAGS: dict[int, str] = {
    1401: "Tech",
    439:  "AI",
    107:  "Business",
    596:  "Culture",
}


# Reject patterns: question shapes where Claude has no edge.

# 1. Price targets. "$150k", "$5.50", "$1,000" — markets price these well
#    and Claude has no real-time data feed.
_PRICE_TARGET_RE = re.compile(r"\$[\d,]+(?:\.\d+)?[kKmMbB]?")

# 2. Compound questions ("X AND Y will happen"). Claude is bad at
#    compound probabilities; market consensus is usually right here.
#    We match "AND" / "BOTH" as standalone words (case-insensitive).
_COMPOUND_RE = re.compile(r"\b(and|both)\b", re.IGNORECASE)


def is_scheduled_event(market: Market) -> bool:
    """Text-pattern check: question looks like a single scheduled event
    we'd actually want to trade, not a price target or compound condition.
    """
    q = market.question or ""
    if _PRICE_TARGET_RE.search(q):
        return False
    if _COMPOUND_RE.search(q):
        return False
    return True


def is_tradeable(market: Market) -> bool:
    """Meta filters: liquidity, time-to-resolution, price extremes."""
    if not market.accepting_orders:
        return False
    if market.liquidity < 500:
        return False
    if market.volume_24hr < 1000:
        return False
    if market.end_date is None:
        return False

    now = datetime.now(timezone.utc)
    if market.end_date < now + timedelta(days=7):
        return False    # too close to resolution, prices already efficient
    if market.end_date > now + timedelta(days=90):
        return False    # capital tied up too long for useful P&L feedback

    if not market.outcome_prices:
        return False    # pre-trading market with no pricing yet
    yes_price = market.outcome_prices[0]
    if yes_price < 0.10 or yes_price > 0.90:
        return False    # fees eat the edge at the extremes

    return True


def screen(markets: list[Market]) -> list[Market]:
    """Apply text + meta filters. Returns the survivors."""
    return [
        m for m in markets
        if is_scheduled_event(m) and is_tradeable(m)
    ]


def fetch_and_screen() -> list[Market]:
    """One-call helper: fetch from each tagged category, screen, dedupe."""
    # Lazy import to keep filters.py independent of gamma.py for unit tests.
    from gamma import fetch_markets

    seen: dict[str, Market] = {}
    for tag_id in SCHEDULED_EVENT_TAGS:
        batch = fetch_markets(tag_id=tag_id, limit=100)
        for m in screen(batch):
            seen.setdefault(m.id, m)    # dedupe; some markets appear in 2 tags
    return list(seen.values())


def main() -> None:
    """Print everything that passes the filters right now."""
    candidates = fetch_and_screen()
    print(f"{len(candidates)} candidates passed the filter pipeline\n")
    for m in candidates:
        yes = m.outcome_prices[0] if m.outcome_prices else None
        days = (m.end_date - datetime.now(timezone.utc)).days if m.end_date else None
        print(f"  Yes={yes:.2%}  in {days}d  vol24h=${m.volume_24hr:>12,.0f}  liq=${m.liquidity:>8,.0f}")
        print(f"    {m.question[:90]}")


if __name__ == "__main__":
    main()
