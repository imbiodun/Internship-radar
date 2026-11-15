import tempfile
import unittest
from pathlib import Path

from app.cache import Cache
from app.config import Settings
from app.llm import LLMService
from pydantic import BaseModel


class Answer(BaseModel):
    value: str


class FakeProvider:
    def __init__(self, name: str, responses: list[str]) -> None:
        self.name = name
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, prompt: str, model: str, json_mode: bool) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


class TestLLMService(unittest.TestCase):
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

    def test_invalid_json_is_retried_then_falls_back(self) -> None:
        first = FakeProvider("anthropic", ["not-json", "still-not-json"])
        second = FakeProvider("gemini", ['{"value":"fallback"}'])
        service = LLMService(
            self.config,
            providers=[first, second],
            cache=Cache(self.config.cache_db_path),
        )

        result = service.complete_json("answer", Answer, "cheap")

        self.assertEqual(result.value, "fallback")
        self.assertEqual(len(first.prompts), 2)
        self.assertIn("Validation error:", first.prompts[1])

    def test_cache_only_rejects_uncached_requests(self) -> None:
        config = self.config
        config = Settings(**{**config.__dict__, "cache_only": True})
        service = LLMService(config, providers=[], cache=Cache(config.cache_db_path))

        with self.assertRaisesRegex(RuntimeError, "CACHE_ONLY"):
            service.complete_text("draft", "strong")
