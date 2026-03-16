import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()

HOST = "https://clob.polymarket.com"
KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 137

creds = ApiCreds(
    api_key=os.getenv("POLYMARKET_API_KEY"),
    api_secret=os.getenv("POLYMARKET_SECRET"),
    api_passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
)

client = ClobClient(HOST, key=KEY, chain_id=CHAIN_ID, creds=creds)

all_markets = []
cursor = "MA=="

while cursor:
    response = client.get_markets(next_cursor=cursor)
    all_markets.extend(response["data"])
    cursor = response.get("next_cursor")
    if cursor == "LTE=":  # Polymarket's "end of results" cursor
        break
    print(f"Fetched {len(all_markets)} markets so far...", end="\r")

print(f"\nTotal markets fetched: {len(all_markets)}")

active = [
    m for m in all_markets
    if m.get("active") and 0.01 < float(m["tokens"][0]["price"]) < 0.99
]
print(f"Active markets: {len(active)}\n")

for market in active[:5]:
    print(market["question"], "| YES price:", market["tokens"][0]["price"])
