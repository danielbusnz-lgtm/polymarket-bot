# Paper Trade Plan

## Goal
Run the LLM pipeline automatically every 6 hours, simulate $10 paper trades,
track P&L in bot.db, and let it run for 1-2 weeks to verify stability.

## Current State
- Pipeline runs manually: `python3 paper_trade.py run`
- Signals logged to `paper_trades.db` (signals table only)
- No dollar amounts tracked, no automatic scheduling

## What Needs to Be Built

### 1. Write positions to bot.db
When a signal fires, insert a row into `bot.db` positions table:
- `is_paper = 1`
- `amount_in = 10.00` (fixed $10 per paper trade)
- `current_value = 10.00` (starts at cost, updated each cron run)
- `title = question`
- `direction = YES or NO`
- `our_prob = avg_prob`
- `market_prob = price`
- `opened_at = unix timestamp`

### 2. Price updater
On each cron run, before logging new signals:
- Fetch current market price for each open paper position
- Update `current_value = amount_in * (current_price / entry_price)` in bot.db
- Mark position closed (remove from positions table) if market resolves

### 3. Cron job
System cron fires every 6 hours:
```
0 */6 * * * cd /path/to/project && python3 paper_trade.py run >> logs/cron.log 2>&1
```

### 4. Cron logger
At the start of each run, write a row to `cron_runs` table in bot.db
so the dashboard countdown timer works.

## Open Questions
- Fixed $10 per trade confirmed?
- Is `.env` with Polymarket API key set up for live price fetching?

## Order of Work
1. Modify `paper_trade.py` — write to bot.db positions on signal
2. Add price update step to cron run
3. Set up cron job + log file
4. Manual end-to-end test (run once, verify positions appear in dashboard)
5. Let run for 1-2 weeks, monitor logs for crashes

## Success Criteria
- Cron fires every 6 hours without crashing
- New signals appear in dashboard Paper tab
- P&L updates each run
- After 1-2 weeks, we have real performance data to evaluate the strategy
