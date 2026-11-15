import tempfile
import unittest
from pathlib import Path

from app.cache import Cache
from app.config import Settings
from app.extract import MAX_SOURCE_TEXT, ExtractionService
from app.search import SearchResult


class FakeExtractor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, prompt: str, schema: object, tier: str) -> object:
        self.calls.append(prompt)
        return schema(
            company="Example Oy",
            title="Software Engineering Intern",
            source_url="https://example.com/jobs/intern",
        )


class TestExtraction(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Settings(
            exa_api_key=None,
            anthropic_api_key=None,
            gemini_api_key=None,
            gemini_base_url=None,
            gemini_model=None,
            verda_api_key=None,
            verda_base_url=None,
            verda_model=None,
            llm_chain=("anthropic",),
            anthropic_cheap_model="cheap",
            anthropic_strong_model="strong",
            cache_only=False,
            cache_db_path=str(Path(self.temp_dir.name) / "cache.db"),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_extracts_from_bounded_evidence_and_caches(self) -> None:
        complete = FakeExtractor()
        result = SearchResult(
            url="https://example.com/jobs/intern",
            highlights=["A real internship posting"],
            text="x" * (MAX_SOURCE_TEXT * 2),
        )
        service = ExtractionService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            complete=complete,
        )

        extracted = service.extract(result)
        cached = service.extract(result)

        self.assertIsNotNone(extracted.posting)
        self.assertTrue(cached.from_cache)
        self.assertEqual(len(complete.calls), 1)
        self.assertLessEqual(len(complete.calls[0]), MAX_SOURCE_TEXT + 500)

    def test_cache_only_returns_source_and_clear_error(self) -> None:
        config = Settings(**{**self.config.__dict__, "cache_only": True})
        result = SearchResult(url="https://example.com/jobs/intern", text="evidence")
        service = ExtractionService(config, cache=Cache(config.cache_db_path))

        extracted = service.extract(result)

        self.assertEqual(str(extracted.source_url), result.url)
        self.assertIsNone(extracted.posting)
        self.assertIn("CACHE_ONLY", extracted.error or "")
