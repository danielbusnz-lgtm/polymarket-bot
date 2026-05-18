"""Normalized Polymarket market data model.

`Market` is the cleaned-up dataclass that downstream code (Claude analysis,
paper broker, ledger) consumes. Gamma returns several fields as JSON-encoded
strings and several numeric fields as strings with `*Num` counterparts;
`Market.from_gamma` handles the translation in one place.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Market:
    id: str
    condition_id: str
    question: str
    slug: str
    description: str
    end_date: datetime | None
    outcomes: list[str]
    outcome_prices: list[float]
    clob_token_ids: list[str]
    volume_24hr: float
    liquidity: float
    accepting_orders: bool
    min_tick_size: float
    min_order_size: float
    neg_risk: bool
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_gamma(cls, raw: dict[str, Any]) -> "Market":
        # Brand-new intraday markets (e.g. "BTC Up or Down - 12:45-12:50PM")
        # are listed before pricing exists; outcomePrices/outcomes can be
        # absent. Treat those as empty lists; downstream filters on
        # `accepting_orders` to skip them.
        return cls(
            id=str(raw["id"]),
            condition_id=raw["conditionId"],
            question=raw["question"],
            slug=raw["slug"],
            description=raw.get("description", ""),
            end_date=_parse_iso(raw.get("endDate")),
            outcomes=_json_list(raw.get("outcomes")),
            outcome_prices=[float(p) for p in _json_list(raw.get("outcomePrices"))],
            clob_token_ids=_json_list(raw.get("clobTokenIds")),
            volume_24hr=float(raw.get("volume24hr") or 0),
            liquidity=float(raw.get("liquidityNum") or 0),
            accepting_orders=bool(raw.get("acceptingOrders", False)),
            min_tick_size=float(raw.get("orderPriceMinTickSize") or 0.01),
            min_order_size=float(raw.get("orderMinSize") or 5),
            neg_risk=bool(raw.get("negRisk", False)),
            raw=raw,
        )


def _json_list(s: Any) -> list:
    """Parse a Gamma JSON-string field that's supposed to be a list. Missing
    or unparseable fields become an empty list rather than raising."""
    if not s:
        return []
    if isinstance(s, list):
        return s
    try:
        out = json.loads(s)
        return out if isinstance(out, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    # Gamma sometimes returns "2026-07-01T04:00:00Z" and sometimes just
    # "2026-07-01" (the endDateIso shortform). Handle both.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
