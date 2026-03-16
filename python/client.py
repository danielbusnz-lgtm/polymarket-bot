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

print(client.get_ok())
