# Polymarket Trading Bot — Master Plan

## Overview
A production-grade autonomous trading bot for Polymarket running three parallel strategies:
- **Arbitrage** — guaranteed profit when YES+NO < $1.00, or price gaps vs Kalshi
- **Whale Copying** — monitor top wallets on-chain, copy large bets fast
- **LLM Mispricing** — Claude analyzes news + data, finds mispriced markets

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   DATA LAYER                        │
│  Polymarket API │ News API │ Whale Wallets │ Kalshi │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│            PYTHON (slow layer)                      │
│  LLM analysis │ Market scanning │ Whale monitoring  │
│  Strategy logic │ Risk management │ Dashboard       │
└────────────────────────┬────────────────────────────┘
                         │ gRPC
┌────────────────────────▼────────────────────────────┐
│            RUST (fast layer)                        │
│  Order execution │ Arbitrage scanner                │
│  WebSocket order book feed │ Kalshi feed            │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│               MONITORING LAYER                      │
│     Dashboard │ Telegram alerts │ Error logging     │
└─────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
polymarket-bot/
├── python/
│   ├── client.py              # authenticated Polymarket client
│   ├── markets.py             # market fetching + filtering
│   ├── strategies/
│   │   ├── llm.py             # Claude analysis + probability estimation
│   │   └── whale.py           # whale wallet monitoring + copy logic
│   └── proto/                 # generated gRPC stubs (Python)
├── rust/
│   ├── src/
│   │   ├── main.rs            # gRPC server entrypoint
│   │   ├── executor.rs        # order placement via CLOB API
│   │   ├── arbitrage.rs       # arbitrage scanner
│   │   └── ws.rs              # WebSocket order book feed
│   └── proto/                 # generated gRPC stubs (Rust)
└── proto/
    └── trader.proto           # shared gRPC definitions
```

---

## Communication Layer

- **Protocol:** gRPC (lowest latency, direct call, no queue hop)
- Python calls Rust when it wants to place an order or read real-time order book data
- Rust owns all WebSocket connections to Polymarket and Kalshi
- Rust executes all trades — Python never touches order placement directly

---

## Strategies

### Strategy 1 — Arbitrage (highest reliability)
- Rust scans all active markets for YES + NO prices that sum to < $1.00
- Cross-platform: compare Polymarket vs Kalshi on same events via WebSocket
- Buy both sides simultaneously, lock in guaranteed profit
- Expected win rate: 85%+

### Strategy 2 — Whale Copying
- Python monitors top Polymarket wallets on Polygon blockchain (public data)
- Detects $10k+ bets from known high-performing wallets
- Sends copy order to Rust via gRPC immediately
- Track wallets: Theo4, Fredi9999, and others with $10M+ lifetime earnings

### Strategy 3 — LLM Mispricing (highest upside)
- Python fetches active markets with meaningful liquidity (>$1k)
- Searches web for recent news relevant to each market
- Feeds question + news context to Claude + calibration data (see Learning System)
- Claude outputs a probability estimate with reasoning
- If |Claude probability - market price| > 5%, sends order to Rust via gRPC
- Kelly Criterion determines position size

---

## Build Phases

### Phase 1 — Foundation (current)
- [ ] Set up folder structure (python/, rust/, proto/)
- [ ] Define gRPC proto file (trader.proto)
- [ ] Build Rust gRPC server (accepts order requests)
- [ ] Build Python gRPC client (sends order requests)
- [ ] Test round-trip: Python → gRPC → Rust → log order

### Phase 2 — LLM Brain + Market Funnel
- [ ] Market funnel: filter 194k markets → ~20 high-value candidates
  - accepting orders, not closed
  - YES price 0.10–0.90
  - spread < 0.05 (liquid)
  - resolves within 30 days
  - scored by urgency + uncertainty
- [ ] Connect Claude Agent SDK (no separate API key needed)
- [ ] Feed market question + news to Claude (Agent SDK built-in WebSearch)
- [ ] Parse Claude probability output (structured JSON)
- [ ] Compare to market price, identify edge (>5% threshold)
- [ ] Send trade signal to Rust via gRPC

### Phase 3 — Arbitrage Scanner (Rust)
- [ ] WebSocket connection to Polymarket order book in Rust
- [ ] Scan for YES+NO < $1.00 in real time
- [ ] Kalshi WebSocket feed + cross-platform comparison
- [ ] Execute both sides simultaneously on signal

### Phase 4 — Whale Wallet Monitor
- [ ] Polygon RPC connection in Python
- [ ] Monitor known high-performing wallet addresses
- [ ] Detect large bets, send copy signal to Rust via gRPC

### Phase 5 — Risk Management
- [ ] Kelly Criterion position sizing
- [ ] Max position cap (10% of bankroll per trade)
- [ ] Real-time P&L tracker
- [ ] Auto-close positions if thesis changes

### Phase 6 — Learning System
- [ ] SQLite trade log: record every bet (market, Claude estimate, market price, edge)
- [ ] On market resolution: record actual outcome + Claude's error
- [ ] Calibration report: aggregate errors by category (crypto, politics, sports, etc.)
- [ ] Feed calibration back to Claude on every run:
  - e.g. "You overestimate YES on crypto by 8% — adjust down"
- [ ] Over time: bot self-corrects and improves accuracy

### Phase 7 — Monitoring
- [ ] Telegram bot for trade alerts
- [ ] Error logging and alerting
- [ ] Ratatui terminal dashboard (Rust) with:
  - Open positions panel (market, YES%, size, edge)
  - P&L panel (today, week, all-time)
  - Recent trades log (scrollable)
  - Bot status panel (last LLM cycle, arb scanner, whale watch)
  - Live updates via internal Rust channel from trading engine
  - Reads historical data from SQLite trade log

---

## Stack

| Component | Language | Tool | Speed |
|---|---|---|---|
| Market data | Python | `py-clob-client` | Slow OK |
| LLM analysis | Python | Claude Agent SDK (Claude Code) | Slow OK |
| Web search for news | Python | Built into Agent SDK (free) | Slow OK |
| Whale tracking | Python | Polygon RPC | Slow OK |
| gRPC client | Python | `grpcio` | Fast |
| gRPC server | Rust | `tonic` | Fast |
| Order execution | Rust | Polymarket CLOB REST | Critical |
| WebSocket feeds | Rust | `tokio-tungstenite` | Critical |
| Arbitrage scanner | Rust | custom | Critical |
| Monitoring | Python | Telegram Bot API | Slow OK |

### Speed Philosophy
- **Slow layer (Python + Agent SDK):** LLM analysis, market scanning, whale monitoring — runs every few minutes, latency doesn't matter
- **Fast layer (Rust):** Order execution, arbitrage scanning, WebSocket feeds — millisecond response time, no Python overhead
- **Bridge:** gRPC — Python sends signals to Rust, Rust executes instantly

---

## Key Numbers (from research)
- $40M+ extracted via arbitrage on Polymarket in 2024-2025
- ilovecircle bot: $2.2M in 2 months, 74% win rate
- Market making win rate: 78-85%
- Avoid markets with liquidity < $1,000 (slippage kills edge)
- Top whale wallets: $22M+ lifetime earnings
