#!/bin/bash
# Runs the paper trade pipeline and logs output.
# Called by crontab — runs twice daily.

PROJECT="/home/python/Projects/personal/polymarket-bot"
LOG="$PROJECT/logs/paper_trade.log"

mkdir -p "$PROJECT/logs"

echo "" >> "$LOG"
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') ===" >> "$LOG"

source "$PROJECT/venv/bin/activate"

cd "$PROJECT" && python3 python/paper_trade.py run >> "$LOG" 2>&1

echo "Exit code: $?" >> "$LOG"
