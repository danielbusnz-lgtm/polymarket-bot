"""
Connection helpers that switch between local SQLite and remote Turso (libSQL)
based on environment variables.

Local dev: no env vars set -> ordinary sqlite3 file connections.
Production / GitHub Actions: set TURSO_*_DATABASE_URL + TURSO_AUTH_TOKEN
and connections go to Turso over HTTP.

Two logical databases:
  - signals  (paper_trades.db)   TURSO_SIGNALS_DATABASE_URL
  - bot      (bot.db)            TURSO_BOT_DATABASE_URL
"""

import os
import sqlite3
from typing import Any


def _connect(local_path: str, remote_url: str | None) -> Any:
    token = os.getenv("TURSO_AUTH_TOKEN")
    if remote_url and token:
        import libsql
        conn = libsql.connect(database=remote_url, auth_token=token)
    else:
        conn = sqlite3.connect(local_path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_signals(local_path: str) -> Any:
    return _connect(local_path, os.getenv("TURSO_SIGNALS_DATABASE_URL"))


def connect_bot(local_path: str) -> Any:
    return _connect(local_path, os.getenv("TURSO_BOT_DATABASE_URL"))
