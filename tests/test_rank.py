import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.cache import Cache
from app.config import Settings
from app.llm import LLMError
from app.models import Posting, Profile
from app.rank import RankedBatch, RankedItem, RankingService


class FakeRanker:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, prompt: str, schema: object, tier: str) -> RankedBatch:
        self.calls += 1
        return schema(
            results=[
                RankedItem(
                    index=0,
                    score=85,
                    reasons=["Matches Python skill"],
                    blockers=[],
                ),
                RankedItem(
                    index=1,
                    score=40,
                    reasons=["Partial match"],
                    blockers=["Finnish language required"],
                ),
            ]
        )


class TestRanking(unittest.TestCase):
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
        self.postings = [
            Posting(
                company="Example Oy",
                title="Python Intern",
                deadline=date(2099, 1, 1),
                source_url="https://example.com/python",
            ),
            Posting(
                company="Old Oy",
                title="Backend Intern",
                deadline=date(2020, 1, 1),
                source_url="https://example.com/backend",
            ),
        ]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ranking_is_batched_and_rechecks_deadlines(self) -> None:
        ranker = FakeRanker()
        service = RankingService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            complete=ranker,
        )

        results = service.rank(self.profile, self.postings)

        self.assertEqual(ranker.calls, 1)
        self.assertEqual(results[0].score, 85)
        self.assertIn("Application deadline has passed", results[1].blockers)

    def test_all_failures_return_unranked_source_preserving_results(self) -> None:
        def fail(prompt: str, schema: object, tier: str) -> RankedBatch:
            raise LLMError("provider unavailable")

        service = RankingService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            complete=fail,
        )

        results = service.rank(self.profile, self.postings)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].score, 0)
        self.assertIn("AI ranking unavailable", results[0].blockers[0])
        self.assertEqual(
            str(results[0].posting.source_url), "https://example.com/python"
        )
