import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    value: Any
    created_at: float


class Cache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def get(self, key: str, ttl_seconds: int) -> CacheEntry | None:
        now = time.time()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value, created_at FROM cache WHERE key = ? AND kind != 'counter'",
                (key,),
            ).fetchone()
            if row is not None and now - row["created_at"] <= ttl_seconds:
                self._increment_counter(connection, "cache_hit")
                return CacheEntry(
                    value=json.loads(row["value"]),
                    created_at=row["created_at"],
                )

            if row is not None:
                connection.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._increment_counter(connection, "cache_miss")
        return None

    def set(self, key: str, kind: str, value: Any) -> float:
        created_at = time.time()
        serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cache (key, kind, value, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    kind = excluded.kind,
                    value = excluded.value,
                    created_at = excluded.created_at
                """,
                (key, kind, serialized, created_at),
            )
        return created_at

    def record_event(self, event: str, provider: str | None = None) -> None:
        counter_key = self._counter_key(event, provider)
        with self._connect() as connection:
            self._increment_counter(connection, event, provider, counter_key)

    def counters(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT key, value FROM cache WHERE kind = 'counter'"
            ).fetchall()
        return {
            row["key"].removeprefix("counter:"): json.loads(row["value"])["count"]
            for row in rows
        }

    @staticmethod
    def key_for(value: Any) -> str:
        serialized = json.dumps(value, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _counter_key(event: str, provider: str | None = None) -> str:
        return f"counter:{event}:{provider}" if provider else f"counter:{event}"

    @classmethod
    def _increment_counter(
        cls,
        connection: sqlite3.Connection,
        event: str,
        provider: str | None = None,
        counter_key: str | None = None,
    ) -> None:
        key = counter_key or cls._counter_key(event, provider)
        row = connection.execute(
            "SELECT value FROM cache WHERE key = ? AND kind = 'counter'",
            (key,),
        ).fetchone()
        count = 0 if row is None else json.loads(row["value"])["count"]
        connection.execute(
            """
            INSERT INTO cache (key, kind, value, created_at)
            VALUES (?, 'counter', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                created_at = excluded.created_at
            """,
            (key, json.dumps({"count": count + 1}), time.time()),
        )
