# Polymarket Trading Bot

An autonomous trading bot for Polymarket built with a Python/Rust hybrid architecture.

## Architecture

Python handles the slow layer (LLM analysis, market scanning). Rust handles the fast layer (order execution, EIP-712 signing, WebSocket feeds). They communicate via gRPC.

```
Python (strategy)  →  gRPC  →  Rust (execution)  →  Polymarket CLOB API
```

## How it works

1. Every 6 hours the LLM pipeline runs — fetches live markets, filters to politics/world events, screens for edge
2. Claude analyzes each candidate across two tiers and outputs a signal (direction, probability, edge)
3. Signals are logged to SQLite — paper trades simulate $10 per signal, live trades place real orders
4. The Rust dashboard shows live P&L, portfolio chart, and countdown to next run

## Strategies

- **LLM mispricing** — Claude estimates true probability and finds markets where the price is wrong
- **Whale copying** — monitors top wallets on Polygon and copies large bets
- **Arbitrage** — scans for YES+NO prices below $1.00 and cross-platform gaps vs Kalshi

## Stack

| Component | Tool |
|---|---|
| Market data | py-clob-client |
| LLM analysis | Claude (Anthropic API) |
| Order signing | EIP-712 via alloy-rs |
| Order execution | Rust + Polymarket CLOB API |
| Auth | L1 EIP-712 + L2 HMAC-SHA256 |
| gRPC bridge | tonic (Rust) + grpcio (Python) |
| Dashboard | Ratatui (Rust TUI) |
| Database | SQLite (signals, positions, snapshots) |

## Paper trading results

6,841 signals logged. 65% win rate on resolved trades.

## Running the pipeline

```bash
# Run the LLM strategy once and log signals
cd python
python3 paper_trade.py run

# View calibration report
python3 paper_trade.py report

# Mark a signal resolved
python3 paper_trade.py resolve <id> YES
```

## Running the dashboard

```bash
cd rust
cargo run --bin dashboard
# Tab to switch between Live / Paper / Demo
# q to quit
```

## Setup

```bash
git clone https://github.com/danielbusnz-lgtm/polymarket-bot
cd polymarket-bot

# Python
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Rust
cd ../rust
cargo build
```

Create a `.env` file in the project root:

```
PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_SECRET=
POLYMARKET_PASSPHRASE=
ANTHROPIC_API_KEY=
```

## Disclaimer

Experimental software. Do not trade with money you cannot afford to lose.
