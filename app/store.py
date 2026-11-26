import sqlite3
import time
import json
from pathlib import Path
from typing import Any
from contextlib import contextmanager
from collections.abc import Generator
from app.models import MatchResult, Profile, SavedPosting


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.path)

        try:
            connection.row_factory = sqlite3.Row

            with connection:
                yield connection

        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_postings (
                    posting_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    saved_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_state (
                    profile_key TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    last_run_at REAL,
                    next_run_at REAL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stats_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_postings (
                    url TEXT PRIMARY KEY,
                    company TEXT,
                    title TEXT,
                    first_seen_at REAL NOT NULL,
                    last_shown_at REAL NOT NULL
                )
                """
            )

    def get_seen_posting(self, url: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT url, company, title, first_seen_at, last_shown_at "
                "FROM seen_postings WHERE url = ?",
                (url,),
            ).fetchone()
        return dict(row) if row is not None else None

    def record_shown_postings(
        self,
        postings: list[Any],
    ) -> None:
        now = time.time()
        with self._connect() as connection:
            for posting in postings:
                url = str(posting.source_url)
                row = connection.execute(
                    "SELECT first_seen_at FROM seen_postings WHERE url = ?",
                    (url,),
                ).fetchone()
                first_seen_at = row["first_seen_at"] if row is not None else now
                connection.execute(
                    """
                    INSERT INTO seen_postings (
                        url, company, title, first_seen_at, last_shown_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        company = excluded.company,
                        title = excluded.title,
                        last_shown_at = excluded.last_shown_at
                    """,
                    (
                        url,
                        posting.company,
                        posting.title,
                        first_seen_at,
                        now,
                    ),
                )

    def log_run_stats(self, stats: Any) -> None:
        created_at = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_stats (stats_json, created_at)
                VALUES (?, ?)
                """,
                (stats.model_dump_json(), created_at),
            )

    def list_run_stats(self, limit: int = 20) -> list[dict[str, Any]]:

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT stats_json, created_at
                FROM run_stats
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {**json.loads(row["stats_json"]), "created_at": row["created_at"]}
            for row in rows
        ]

    def save_match(
        self,
        posting_id: str,
        profile: Profile,
        match: MatchResult,
    ) -> SavedPosting:
        saved_at = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO saved_postings (
                    posting_id, profile_json, match_json, saved_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(posting_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    match_json = excluded.match_json,
                    saved_at = excluded.saved_at
                """,
                (
                    posting_id,
                    profile.model_dump_json(),
                    match.model_dump_json(),
                    saved_at,
                ),
            )
        return SavedPosting(
            posting_id=posting_id,
            posting=match.posting,
            profile=profile,
            score=match.score,
            reasons=match.reasons,
            blockers=match.blockers,
            saved_at=saved_at,
        )

    def list_saved(self) -> list[SavedPosting]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT posting_id, profile_json, match_json, saved_at
                FROM saved_postings
                ORDER BY saved_at DESC
                """
            ).fetchall()
            saved_postings = []

        for row in rows:
            match = MatchResult.model_validate_json(row["match_json"])

            profile = Profile.model_validate_json(row["profile_json"])

            saved_posting = SavedPosting(
                posting_id=row["posting_id"],
                posting=match.posting,
                profile=profile,
                score=match.score,
                reasons=match.reasons,
                blockers=match.blockers,
                saved_at=row["saved_at"],
            )

            saved_postings.append(saved_posting)

        return saved_postings

    def delete_saved(self, posting_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM saved_postings WHERE posting_id = ?",
                (posting_id,),
            )
            return cursor.rowcount > 0

    def set_monitor_profile(
        self,
        profile_key: str,
        profile: Profile,
        next_run_at: float | None = None,
    ) -> dict[str, Any]:
        updated_at = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO monitor_state (
                    profile_key, profile_json, last_run_at, next_run_at, updated_at
                ) VALUES (?, ?, NULL, ?, ?)
                ON CONFLICT(profile_key) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    next_run_at = excluded.next_run_at,
                    updated_at = excluded.updated_at
                """,
                (
                    profile_key,
                    profile.model_dump_json(),
                    next_run_at,
                    updated_at,
                ),
            )
        return {
            "profile_key": profile_key,
            "profile": profile,
            "next_run_at": next_run_at,
            "updated_at": updated_at,
        }
