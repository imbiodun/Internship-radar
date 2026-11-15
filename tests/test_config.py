import os
import unittest
from unittest.mock import patch

from app.config import load_settings


class TestConfig(unittest.TestCase):
    def test_defaults_are_safe_for_local_setup(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.llm_chain, ("anthropic", "gemini", "verda"))
        self.assertFalse(settings.cache_only)
        self.assertEqual(settings.max_queries_per_run, 5)
        self.assertEqual(settings.max_results_per_query, 10)

    def test_environment_values_are_loaded(self) -> None:
        values = {
            "EXA_API_KEY": "exa-test",
            "LLM_CHAIN": "gemini, verda",
            "CACHE_ONLY": "true",
            "CACHE_DB_PATH": "test-radar.db",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = load_settings()

        self.assertEqual(settings.exa_api_key, "exa-test")
        self.assertEqual(settings.llm_chain, ("gemini", "verda"))
        self.assertTrue(settings.cache_only)
        self.assertEqual(settings.cache_db_path, "test-radar.db")
