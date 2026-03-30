#!/bin/bash
# Runs the paper trade pipeline and logs output.
# Called by crontab — runs twice daily.

PROJECT="/home/dan/Projects/Personal/signum"
LOG="$PROJECT/logs/paper_trade.log"

mkdir -p "$PROJECT/logs"

echo "" >> "$LOG"
echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') ===" >> "$LOG"

PYTHON="$PROJECT/.venv/bin/python"

cd "$PROJECT/python" && "$PYTHON" paper_trade.py run >> "$LOG" 2>&1

echo "Exit code: $?" >> "$LOG"
