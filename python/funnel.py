import os
import json
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()

# --- Config ---
MAX_CANDIDATES    = 20
MIN_YES_PRICE     = 0.05    # skip near-certain NO (research: edge exists down to 5%)
MAX_YES_PRICE     = 0.95    # skip near-certain YES
MAX_SPREAD        = 0.03    # tight spread = liquid market (arb needs >2.5% to be profitable)
MAX_DAYS_TO_CLOSE = 30      # near-term only — more price movement as resolution approaches
MIN_VOLUME        = 5000    # minimum $5k 24hr volume — avoid illiquid traps


def get_client() -> ClobClient:
    return ClobClient(
        "https://clob.polymarket.com",
        key=os.getenv("PRIVATE_KEY"),
        chain_id=137,
        creds=ApiCreds(
            api_key=os.getenv("POLYMARKET_API_KEY"),
            api_secret=os.getenv("POLYMARKET_SECRET"),
            api_passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
        ),
    )

def fetch_candidates() -> list[dict]:
    now = datetime.now(timezone.utc)
    end_date_max = (now + timedelta(days=MAX_DAYS_TO_CLOSE)).isoformat()

    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "volume_num_min": MIN_VOLUME,
        "end_date_max": end_date_max,
        "limit": 500,
    }

    response = requests.get("https://gamma-api.polymarket.com/markets", params=params)
    response.raise_for_status()
    markets = response.json()

    candidates = []
    for m in markets:
        # skip markets with missing price data
        if not m.get("outcomePrices") or len(m["outcomePrices"]) < 2:
            continue

        prices    = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
        yes_price = float(prices[0])
        no_price  = float(prices[1])

        # skip near-certain outcomes
        if not (MIN_YES_PRICE <= yes_price <= MAX_YES_PRICE):
            continue

        # skip illiquid markets (spread too wide)
        spread = abs(1.0 - (yes_price + no_price))
        if spread > MAX_SPREAD:
            continue

        # skip sports markets — politics/world events only
        if m.get("sportsMarketType") is not None:
            continue

        m["yes_price"] = yes_price
        m["no_price"]  = no_price
        m["spread"]    = round(spread, 4)
        candidates.append(m)

    print(f"Gamma API returned: {len(markets)} markets")
    print(f"After filtering:    {len(candidates)} candidates")
    return candidates[:MAX_CANDIDATES]


def print_candidates(candidates: list[dict]) -> None:
    print(f"\n{'YES':>5}  {'Spread':>6}  Question")
    print("-" * 80)
    for m in candidates:
        print(f"{m['yes_price']:>5.2f}  {m['spread']:>6.4f}  {m['question'][:65]}")


if __name__ == "__main__":
    candidates = fetch_candidates()
    print_candidates(candidates)
