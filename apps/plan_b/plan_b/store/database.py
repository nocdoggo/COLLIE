"""SQLite access with explicit transactions.

Connections use ``isolation_level=None`` so the sqlite3 module never opens implicit
transactions (works on Python 3.11 and 3.12). Every write path runs inside
``BEGIN IMMEDIATE``: SQLite takes the write lock before the first read, so two writers cannot
both read the same capacity or revision and then both write. WAL mode lets readers proceed
while a writer holds the lock.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path, isolation_level=None, timeout=30.0, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            try:
                yield conn
            finally:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def migrate(self) -> list[str]:
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
            done: list[str] = []
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = path.stem
                if version in applied:
                    continue
                stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                script = (
                    "BEGIN IMMEDIATE;\n"
                    + path.read_text()
                    + f"\nINSERT INTO schema_migrations (version, applied_at) "
                    f"VALUES ('{version}', '{stamp}');\nCOMMIT;\n"
                )
                try:
                    conn.executescript(script)
                except BaseException:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
                done.append(version)
            return done
        finally:
            conn.close()

    def schema_versions(self) -> list[str]:
        with self.read() as conn:
            return [r["version"] for r in conn.execute("SELECT version FROM schema_migrations")]
