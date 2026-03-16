# Polymarket Trading Bot

An autonomous trading bot for Polymarket built with a Python/Rust hybrid architecture.

## Architecture

Python handles the slow layer (LLM analysis, market scanning, whale monitoring). Rust handles the fast layer (order execution, arbitrage scanning, WebSocket feeds). They communicate via gRPC.

```
Python (strategy)  →  gRPC  →  Rust (execution)
```

## Strategies

- **Arbitrage** — scans for YES+NO prices below $1.00 and cross-platform gaps vs Kalshi
- **Whale copying** — monitors top wallets on Polygon and copies large bets
- **LLM mispricing** — uses Claude to estimate true probability and find mispriced markets

## Stack

| Component | Tool |
|---|---|
| Market data | py-clob-client |
| LLM analysis | Claude Agent SDK |
| Order execution | Rust + Polymarket CLOB API |
| WebSocket feeds | tokio-tungstenite |
| gRPC bridge | tonic (Rust) + grpcio (Python) |
| Dashboard | Ratatui (Rust TUI) |
| Trade log | SQLite |

## Status

Work in progress. Building in public.

## Setup

```bash
git clone https://github.com/yourusername/polymarket-bot
cd polymarket-bot

# Python
python3 -m venv venv
source venv/bin/activate
pip install py-clob-client python-dotenv anthropic

# Rust
cd rust
cargo build
```

Create a `.env` file in the root (see `.env.example`).

## Disclaimer

This is experimental software. Do not trade with money you cannot afford to lose.
