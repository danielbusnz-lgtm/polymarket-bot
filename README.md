<!-- Badges -->
[![Python](https://img.shields.io/badge/python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License](https://img.shields.io/github/license/danielbusnz-lgtm/signum?style=flat-square)](LICENSE)

# signum

Autonomous prediction market trading on Polymarket. Uses multi-LLM consensus to find mispriced markets and executes orders via the Polymarket CLOB API.

**Paper trading: 6,841 signals logged, 65% win rate on resolved trades.**

## Why

Prediction markets price events as probabilities, but they're often wrong on politics and world events where LLMs have strong priors. This bot finds those mispricings automatically: five LLMs vote on what the true probability should be, and when they agree the market is off by 12%+, it trades.

## How It Works

1. **Every 6 hours**, the pipeline fetches live markets from Polymarket's Gamma API
2. **Funnel** filters to liquid, tradable candidates (spread < 3%, volume >= $5k, 5-95% price range)
3. **Tier 1 screen**: Claude picks the top 5 markets worth analyzing
4. **Tier 2 analysis**: 5 LLMs independently estimate the true probability, with fresh news context from Tavily
5. **Signal**: If consensus edge >= 12% and disagreement <= 15%, log a trade signal
6. **Execution**: Order placed via py-clob-client to Polymarket's CLOB

See the [architecture diagram](#architecture) below for the full pipeline.

## LLM Consensus Engine

Five models vote independently on each market (minimum 3 required):

| Model | Provider | Required |
|-------|----------|----------|
| Claude Opus | Anthropic | Yes |
| GPT-4o | OpenAI | No |
| Gemini 2.5 Flash | Google | No |
| Grok-3 | xAI | No |
| DeepSeek Reasoner | DeepSeek | No |

The highest and lowest estimates are dropped. The middle three are averaged to produce the consensus probability. A signal fires when this consensus diverges from the market price by at least 12 percentage points, with less than 15% disagreement among models.

## Architecture

![Architecture Diagram](diagrams/architecture.png)

### Python Files

| File | Purpose |
|------|---------|
| `funnel.py` | Fetch and filter market candidates from Gamma API |
| `strategies/llm.py` | Multi-LLM consensus analysis (Tier 1 screen + Tier 2 deep analysis) |
| `paper_trade.py` | CLI for paper trading: run pipeline, view reports, resolve signals |
| `client.py` | Polymarket CLOB client initialization |
| `api.py` | FastAPI backend for web dashboard |
| `check_setup.py` | Validate your credentials before running |

## Stack

| Layer | Technology |
|-------|-----------|
| Market data | Polymarket Gamma API, py-clob-client |
| LLM analysis | Claude, GPT-4o, Gemini, Grok, DeepSeek |
| News context | Tavily search API |
| Order execution | py-clob-client (EIP-712 signing built-in) |
| Web dashboard | Next.js 16, Tailwind, Recharts, TradingView Lightweight Charts |
| Database | SQLite (signals, positions, portfolio snapshots) |
| Scheduling | Cron (every 6 hours) |

## Getting Started

### Prerequisites

- Python 3.13+ and [uv](https://docs.astral.sh/uv/) (or pip)
- [Node.js 22+](https://nodejs.org/) and [pnpm](https://pnpm.io/) (for the web dashboard)
- A Polymarket account with API credentials (see [Polymarket Setup](#polymarket-setup))
- API keys for at least 3 LLM providers (Anthropic required, plus 2 others)
- Tavily API key for news context

### Setup

```bash
git clone https://github.com/danielbusnz-lgtm/signum
cd signum
```

**Python** (uses [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

Or with pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

**Web dashboard:**

```bash
cd web
pnpm install
```

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

### Validate Setup

Before running the bot, validate your credentials:

```bash
cd python
python check_setup.py
```

This checks all API keys and shows which LLMs are available.

### Paper Trading

```bash
cd python

# Run the full pipeline once and log signals to SQLite
python paper_trade.py run

# View calibration report (win rate by edge bucket)
python paper_trade.py report

# Mark a signal as resolved
python paper_trade.py resolve <id> YES
```

### Live Trading

```bash
cd python

# Run with --live to place real orders
python paper_trade.py run --live
```

**Warning:** This places real orders with real money. Start small.

### Web Dashboard

```bash
# Terminal 1: Start the API server
.venv/bin/uvicorn python.api:app --port 8888

# Terminal 2: Start the Next.js frontend
cd web && pnpm dev
```

Open `http://localhost:3000`. The dashboard shows an equity curve, open positions with live prices, KPI strip (win rate, Sharpe, drawdown), and an analytics page with calibration charts and model health.

### GitHub Actions (Turso)

The pipeline can also run on a schedule via GitHub Actions, with state persisted to [Turso](https://turso.tech) (remote SQLite). See `.github/workflows/paper-trade.yml`.

**Setup:**

1. Create two Turso databases (signals + bot state):
   ```bash
   turso db create signum-signals
   turso db create signum-bot
   turso db show --url signum-signals  # -> TURSO_SIGNALS_DATABASE_URL
   turso db show --url signum-bot      # -> TURSO_BOT_DATABASE_URL
   turso db tokens create signum-signals  # -> TURSO_AUTH_TOKEN (one token works for both DBs in the same group)
   ```

2. Add these as repo secrets (`Settings > Secrets and variables > Actions`):
   - `TURSO_AUTH_TOKEN`
   - `TURSO_SIGNALS_DATABASE_URL`
   - `TURSO_BOT_DATABASE_URL`
   - `ANTHROPIC_API_KEY` (required), plus any of `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `XAI_API_KEY`, `DEEPSEEK_API_KEY` (need >= 2 to satisfy the 3-model minimum with Claude)
   - `TAVILY_API_KEY`

3. The workflow runs every 6h. Manually trigger with the Run workflow button on the Actions tab.

**Local dev** keeps using the SQLite files (`paper_trades.db`, `bot.db`) when the Turso env vars are unset — no behaviour change.

## Polymarket Setup

To trade on Polymarket, you need:

### 1. Create a Polymarket Account

1. Go to [polymarket.com](https://polymarket.com) and connect a wallet (MetaMask, Coinbase Wallet, etc.)
2. Your wallet must be on Polygon network
3. Deposit USDC to fund your account

### 2. Get API Credentials

1. Go to [polymarket.com/settings](https://polymarket.com/settings)
2. Navigate to the API section
3. Generate API credentials (you'll get API key, secret, and passphrase)
4. **Important:** Save these immediately, the secret is only shown once

### 3. Export Your Private Key

Your wallet's private key is needed for signing orders:

- **MetaMask:** Settings > Security & Privacy > Reveal Secret Recovery Phrase (then derive private key)
- **Or:** Export from your wallet provider's settings

**Never share your private key. Never commit it to git.**

### 4. Fill in .env

```bash
PRIVATE_KEY=your_polygon_wallet_private_key
POLYMARKET_API_KEY=your_api_key
POLYMARKET_SECRET=your_base64_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

## Project Structure

```
├── python/
│   ├── paper_trade.py           # Main CLI (run, report, resolve)
│   ├── funnel.py                # Market candidate filtering
│   ├── strategies/llm.py        # Multi-LLM consensus engine
│   ├── api.py                   # FastAPI backend for web dashboard
│   ├── client.py                # CLOB client init
│   ├── check_setup.py           # Credential validation
│   └── seed_mock_data.py        # Generate mock data for development
├── web/                         # Next.js 16 dashboard
│   ├── app/(dashboard)/         # Dashboard + analytics pages
│   ├── components/dashboard/    # Equity curve, positions, charts
│   └── lib/                     # API client, hooks, metrics
├── diagrams/                    # Architecture diagrams
└── .env.example
```

## Disclaimer

Experimental software. Do not trade with money you cannot afford to lose.
