import tempfile
import unittest
from pathlib import Path

from app.cache import Cache
from app.config import Settings
from app.draft import DraftInput, DraftService
from app.models import Posting, Profile


class TestDraft(unittest.TestCase):
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
        self.profile = Profile(
            role="Software Engineer",
            skills=["Python"],
            location="Finland",
            languages=["English"],
            work_authorization="Eligible",
        )
        self.posting = Posting(
            company="Example Oy",
            title="Python Intern",
            source_url="https://example.com/python",
        )
        self.input = DraftInput(
            profile=self.profile,
            posting=self.posting,
            posting_id="example-python-intern",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_draft_uses_strong_tier_and_source(self) -> None:
        calls: list[str] = []

        def complete(prompt: str, tier: str) -> str:
            calls.append(tier)
            return "I am interested in this software engineering internship."

        service = DraftService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            complete=complete,
        )

        draft = service.draft(self.input)

        self.assertEqual(calls, ["strong"])
        self.assertEqual(draft.sources_used, [self.posting.source_url])
        self.assertIn("interested", draft.text)
