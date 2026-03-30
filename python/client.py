import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

load_dotenv()


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
