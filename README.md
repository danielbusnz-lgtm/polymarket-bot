# Oracle

AI-driven paper-trading bot for [Polymarket](https://polymarket.com) prediction markets.

## What it does

1. Pulls active markets from Polymarket's Gamma API
2. Filters down to "will [scheduled event] happen by [date]?" style markets where LLM reasoning has potential edge (tech launches, M&A deadlines, IPOs, etc.)
3. Has Claude research each market with web search + extended thinking, then estimate the probability of "Yes"
4. Persists every prediction with full reasoning, token usage, and cost to a local SQLite ledger
5. Skips re-scanning markets already predicted within the rescan window

## Status

| | |
|---|---|
| Data fetch + parse | done |
| Market filtering | done |
| Claude-powered prediction | done |
| SQLite persistence + cost tracking | done |
| Dedupe (skip recently-scanned) | done |
| CI on every push | done |
| Paper order placement | TODO (`broker.py`) |
| Fill detection + equity curve | TODO |

Currently accumulating predictions. No real trades placed.

## Quick start

```bash
git clone git@github.com:danielbusnz-lgtm/Oracle.git
cd Oracle
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Add Anthropic API key
echo "ANTHROPIC_API_KEY=sk-..." > .env

# Initialize the SQLite ledger
python ledger.py

# Run one prediction
python analyst.py
```

## Architecture

```
gamma.py     Polymarket Gamma API client
market.py    Market dataclass + parse helpers
filters.py   Screen for high-edge markets (tag + regex)
analyst.py   Claude predict (web search + extended thinking)
ledger.py    SQLite schema, connect, init, migrate
repo.py      Data-access helpers (insert/query/cost tracking)
```

Predictions, snapshots, orders, and equity all link by ID so any past decision can be reconstructed from the database.

## Cost per prediction

Driven by model choice + how aggressively Claude searches:

| Model | Settings | Approx cost |
|---|---|---|
| Sonnet 4.6 (current) | medium thinking, 5 searches | ~$0.28 |
| Opus 4.7 | high thinking, 10 searches | ~$1.25 |
| Haiku 4.5 | no thinking, 5 searches | ~$0.05 |

About 70% of the cost is web-search result content getting fed back as input tokens. Lower `MAX_SEARCHES` in `analyst.py` to cut spend.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API access |
| `RESCAN_TTL_HOURS` | `24` | Skip re-predicting same market within this window |

## Tests

```bash
python tests/test_repo.py        # repo helpers, real Polymarket data
python tests/parser_smoke.py     # parser regression across many markets
```

CI runs both on every push to `master`.

## Stack

Python 3.13, httpx, anthropic SDK, stdlib sqlite3. Docker + Fly.io configured but not used yet. No ORM, no service framework — just functions and files.
