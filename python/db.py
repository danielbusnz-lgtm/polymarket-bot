"""
Connection helpers that switch between local SQLite and remote Turso (libSQL)
based on environment variables.

Local dev: no env vars set -> ordinary sqlite3 file connections.
Production / GitHub Actions: set TURSO_*_DATABASE_URL + TURSO_AUTH_TOKEN
and connections go to Turso over HTTP.

libsql connections return plain tuples and don't accept `row_factory`, so we
wrap them in a thin adapter that mimics sqlite3.Row + commit-on-context-exit.

Two logical databases:
  - signals  (paper_trades.db)   TURSO_SIGNALS_DATABASE_URL
  - bot      (bot.db)            TURSO_BOT_DATABASE_URL
"""

import os
import sqlite3
from typing import Any


class _Row:
    __slots__ = ("_data", "_keys")

    def __init__(self, data: tuple, keys: list[str]) -> None:
        self._data = data
        self._keys = keys

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._data[self._keys.index(key)]
        return self._data[key]

    def keys(self) -> list[str]:
        return self._keys

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


class _Cursor:
    def __init__(self, cur: Any) -> None:
        self._cur = cur
        desc = cur.description
        self._keys = [d[0] for d in desc] if desc else []

    def fetchone(self):
        r = self._cur.fetchone()
        return _Row(r, self._keys) if r is not None else None

    def fetchall(self):
        return [_Row(r, self._keys) for r in self._cur.fetchall()]

    def __iter__(self):
        return self

    def __next__(self):
        r = self._cur.fetchone()
        if r is None:
            raise StopIteration
        return _Row(r, self._keys)

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _Connection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.row_factory = None  # accepted but ignored

    def execute(self, sql: str, params: tuple = ()):
        return _Cursor(self._conn.execute(sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            try:
                self._conn.rollback()
            except Exception:
                pass
        return False

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _connect(local_path: str, remote_url: str | None, token: str | None) -> Any:
    if remote_url and token:
        import libsql
        return _Connection(libsql.connect(database=remote_url, auth_token=token))
    conn = sqlite3.connect(local_path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_signals(local_path: str) -> Any:
    return _connect(
        local_path,
        os.getenv("TURSO_SIGNALS_DATABASE_URL"),
        os.getenv("TURSO_SIGNALS_AUTH_TOKEN") or os.getenv("TURSO_AUTH_TOKEN"),
    )


def connect_bot(local_path: str) -> Any:
    return _connect(
        local_path,
        os.getenv("TURSO_BOT_DATABASE_URL"),
        os.getenv("TURSO_BOT_AUTH_TOKEN") or os.getenv("TURSO_AUTH_TOKEN"),
    )
