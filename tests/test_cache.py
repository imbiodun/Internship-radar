import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.cache import Cache


class TestCache(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache = Cache(Path(self.temp_dir.name) / "cache.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_key_for_is_stable_for_equivalent_input(self) -> None:
        first = Cache.key_for({"query": "internship", "limit": 10})
        second = Cache.key_for({"limit": 10, "query": "internship"})

        self.assertEqual(first, second)

    def test_get_returns_cached_value_and_records_hit(self) -> None:
        key = Cache.key_for({"query": "internship"})
        self.cache.set(key, "exa_search", {"results": [1, 2]})

        entry = self.cache.get(key, ttl_seconds=60)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.value, {"results": [1, 2]})
        self.assertEqual(self.cache.counters()["cache_hit"], 1)

    def test_expired_value_is_not_returned_and_records_miss(self) -> None:
        key = Cache.key_for({"query": "internship"})
        with patch("app.cache.time.time", return_value=100.0):
            self.cache.set(key, "exa_search", {"results": []})
        with patch("app.cache.time.time", return_value=161.0):
            entry = self.cache.get(key, ttl_seconds=60)

        self.assertIsNone(entry)
        self.assertEqual(self.cache.counters()["cache_miss"], 1)

    def test_provider_events_are_counted(self) -> None:
        self.cache.record_event("llm_call", "anthropic")
        self.cache.record_event("llm_call", "anthropic")
        self.cache.record_event("exa_call", "exa")

        self.assertEqual(
            self.cache.counters(),
            {"llm_call:anthropic": 2, "exa_call:exa": 1},
        )
