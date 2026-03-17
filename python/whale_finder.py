import requests
import time

# Top 20 wallets from Polymarket leaderboard (monthly profit, March 2026)
LEADERBOARD_WALLETS = [
    {"username": "HorizonSplendidView", "address": "0x02227b8f5a9636e895607edd3185ed6ee5598ff7"},
    {"username": "beachboy4",           "address": "0xc2e7800b5af46e6093872b177b7a5e7f0563be51"},
    {"username": "majorexploiter",      "address": "0x019782cab5d844f02bafb71f512758be78579f3c"},
    {"username": "CemeterySun",         "address": "0x37c1874a60d348903594a96703e0507c518fc53a"},
    {"username": "Countryside",         "address": "0xbddf61af533ff524d27154e589d2d7a81510c684"},
    {"username": "0x2a2C53bD",          "address": "0x2a2c53bd278c04da9962fcf96490e17f3dfb9bc1"},
    {"username": "432614799197",        "address": "0xdc876e6873772d38716fda7f2452a78d426d7ab6"},
    {"username": "0p0jogggg",           "address": "0x6ac5bb06a9eb05641fd5e82640268b92f3ab4b6e"},
    {"username": "gatorr",              "address": "0x93abbc022ce98d6f45d4444b594791cc4b7a9723"},
    {"username": "bcda",                "address": "0xb45a797faa52b0fd8adc56d30382022b7b12192c"},
    {"username": "swisstony",           "address": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
    {"username": "gmanas",              "address": "0xe90bec87d9ef430f27f9dcfe72c34b76967d5da2"},
    {"username": "GamblingIsAllYouNeed","address": "0x507e52ef684ca2dd91f90a9d26d149dd3288beae"},
    {"username": "waterbottle6",        "address": "0xb90494d9a5d8f71f1930b2aa4b599f95c344c255"},
    {"username": "geniusMC",            "address": "0x0b9cae2b0dfe7a71c413e0604eaac1c352f87e44"},
    {"username": "WoofMaster",          "address": "0x916f7165c2c836aba22edb6453cdbb5f3ea253ba"},
    {"username": "HedgeMaster88",       "address": "0x036c159d5a348058a81066a76b89f35926d4178d"},
    {"username": "SecondWindCapital",   "address": "0x8c80d213c0cbad777d06ee3f58f6ca4bc03102c3"},
    {"username": "huhaoli",             "address": "0xf19d7d88cf362110027dcd64750fdd209a04276f"},
    {"username": "anoin123",            "address": "0x96489abcb9f583d6835c8ef95ffc923d05a86825"},
]

# Sports slug prefixes — used to detect and skip sports markets
SPORTS_PREFIXES = (
    "epl-", "ucl-", "nba-", "nhl-", "nfl-", "mlb-", "mls-", "uel-",
    "lal-", "fl1-", "sea-", "efl-", "efa-", "bun-", "nba", "ncaa-",
    "ufc-", "atp-", "wta-", "f1-", "golf-", "boxing-",
)

SPORTS_TITLE_KEYWORDS = (
    " FC ", "win on", "Spread:", " vs. ", "Grizzlies", "Lakers", "Warriors",
    "Celtics", "Knicks", "Cavaliers", "Thunder", "Rockets", "Nuggets",
)


def is_sports(position: dict) -> bool:
    slug  = position.get("slug", "")
    title = position.get("title", "")
    if any(slug.startswith(p) for p in SPORTS_PREFIXES):
        return True
    if any(kw in title for kw in SPORTS_TITLE_KEYWORDS):
        return True
    return False


def fetch_closed_positions(address: str) -> list[dict]:
    url    = f"https://data-api.polymarket.com/closed-positions?user={address}&limit=500"
    r      = requests.get(url, timeout=10)
    r.raise_for_status()
    data   = r.json()
    # API returns either a list or a dict with a results key
    if isinstance(data, list):
        return data
    return data.get("data", data.get("results", []))


def analyze_wallet(wallet: dict) -> dict | None:
    username = wallet["username"]
    address  = wallet["address"]

    try:
        positions = fetch_closed_positions(address)
    except Exception as e:
        print(f"  ERROR fetching {username}: {e}")
        return None

    if not positions:
        print(f"  {username}: no closed positions")
        return None

    total     = len(positions)
    wins      = sum(1 for p in positions if float(p.get("realizedPnl", 0)) > 0)
    win_rate  = wins / total if total > 0 else 0
    total_pnl = sum(float(p.get("realizedPnl", 0)) for p in positions)

    print(f"  {username}: {total} trades | win rate {win_rate:.1%} | PnL ${total_pnl:,.0f}")

    return {
        "username":  username,
        "address":   address,
        "trades":    total,
        "win_rate":  win_rate,
        "total_pnl": total_pnl,
    }


def main():
    print("Analyzing leaderboard wallets for politics/world events alpha...\n")

    results = []
    for wallet in LEADERBOARD_WALLETS:
        print(f"Checking {wallet['username']}...")
        result = analyze_wallet(wallet)
        if result is not None:
            results.append(result)
        time.sleep(0.3)  # be polite to the API

    # Filter: 65%+ win rate, 100+ trades, positive PnL
    qualified = [
        r for r in results
        if r["win_rate"] >= 0.65 and r["trades"] >= 100 and r["total_pnl"] > 0
    ]

    print(f"\n{'='*60}")
    print(f"QUALIFIED WHALE WALLETS ({len(qualified)} found)")
    print(f"Criteria: 65%+ win rate, 100+ trades, positive PnL")
    print(f"{'='*60}")

    if not qualified:
        print("\nNone found. These leaderboard wallets are likely sports traders.")
        print("Consider expanding the wallet list beyond the leaderboard.")
    else:
        qualified.sort(key=lambda r: r["win_rate"], reverse=True)
        for r in qualified:
            print(f"\n  {r['username']}")
            print(f"  Address:  {r['address']}")
            print(f"  Trades:   {r['pol_trades']}")
            print(f"  Win rate: {r['win_rate']:.1%}")
            print(f"  PnL:      ${r['total_pnl']:,.0f}")


if __name__ == "__main__":
    main()
