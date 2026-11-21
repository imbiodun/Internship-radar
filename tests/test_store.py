import tempfile
import unittest
from pathlib import Path

from app.models import MatchResult, Posting, Profile, RunStats
from app.store import Store


class TestStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp_dir.name) / "radar.db")
        self.profile = Profile(
            role="Software Engineer",
            location="Finland",
            work_authorization="Eligible",
        )
        self.posting = Posting(
            company="Example Oy",
            title="Python Intern",
            source_url="https://example.com/python",
        )
        self.match = MatchResult(
            posting=self.posting,
            score=80,
            reasons=["Python match"],
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_list_and_delete_posting(self) -> None:
        saved = self.store.save_match("example-python", self.profile, self.match)

        listed = self.store.list_saved()

        self.assertEqual(saved.posting_id, "example-python")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].posting.title, "Python Intern")
        self.assertTrue(self.store.delete_saved("example-python"))
        self.assertEqual(self.store.list_saved(), [])

    def test_monitor_state_is_persisted(self) -> None:
        state = self.store.set_monitor_profile(
            "finland-software",
            self.profile,
            next_run_at=1890000000,
        )

        self.assertEqual(state["profile_key"], "finland-software")
        self.assertEqual(state["next_run_at"], 1890000000)

    def test_run_stats_are_logged_and_listed(self) -> None:
        stats = RunStats(
            searched=20,
            deduped=15,
            extracted=8,
            extraction_failed=7,
            shown=8,
        )

        self.store.log_run_stats(stats)
        listed = self.store.list_run_stats(limit=20)

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["searched"], 20)
        self.assertEqual(listed[0]["deduped"], 15)

    def test_seen_postings_are_recorded_persistently(self) -> None:
        self.store.record_shown_postings([self.posting])

        first = self.store.get_seen_posting(str(self.posting.source_url))
        self.store.record_shown_postings([self.posting])
        second = self.store.get_seen_posting(str(self.posting.source_url))

        self.assertIsNotNone(first)
        self.assertEqual(first["url"], str(self.posting.source_url))
        self.assertEqual(first["first_seen_at"], second["first_seen_at"])
