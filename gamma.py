"""Polymarket Gamma API client.

Thin wrapper around Polymarket's `gamma-api.polymarket.com` REST endpoints.
Reads market metadata and hands it to `Market.from_gamma` for normalization.
No auth required for read endpoints.
"""

import httpx

from market import Market

HOST = "https://gamma-api.polymarket.com"


def fetch_top_market() -> Market:
    """Pull the single highest-volume currently-active market from Gamma."""
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": 1,
    }
    url = f"{HOST}/markets"
    resp = httpx.get(url, params=params, timeout=15.0)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list) or not body:
        raise RuntimeError(f"unexpected source response: {body!r}")
    return Market.from_gamma(body[0])


def fetch_markets(
    tag_id: int | None = None,
    limit: int = 100,
    **extra_params: str | int,
) -> list[Market]:
    """Fetch a batch of currently-tradeable markets, optionally tag-filtered.

    Caller-provided `extra_params` are passed through to Gamma as-is — useful
    for ad-hoc tweaks like `order='endDate'` or `liquidity_num_min=1000`.
    """
    params: dict[str, str | int] = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": limit,
    }
    if tag_id is not None:
        params["tag_id"] = tag_id
    params.update(extra_params)

    resp = httpx.get(f"{HOST}/markets", params=params, timeout=20.0)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list):
        raise RuntimeError(f"unexpected source response: {body!r}")
    return [Market.from_gamma(raw) for raw in body]


def main() -> None:
    market = fetch_top_market()
    pairs = list(zip(market.outcomes, market.outcome_prices))
    print(f"{market.question}")
    print(f"  id           : {market.id}")
    print(f"  slug         : {market.slug}")
    print(f"  ends         : {market.end_date}")
    print(f"  outcomes     : {pairs}")
    print(f"  volume_24hr  : ${market.volume_24hr:,.0f}")
    print(f"  liquidity    : ${market.liquidity:,.0f}")
    print(f"  min_tick     : {market.min_tick_size}")
    print(f"  min_order    : ${market.min_order_size}")
    print(f"  neg_risk     : {market.neg_risk}")
    print(f"  trading      : {market.accepting_orders}")
    print(f"  tokens       : {market.clob_token_ids}")


if __name__ == "__main__":
    main()
