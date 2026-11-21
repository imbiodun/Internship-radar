import tempfile
import unittest
from pathlib import Path

from app.cache import Cache
from app.config import Settings
from app.models import Profile
from app.search import SearchService, build_queries


class FakeResult:
    def __init__(self, url: str, title: str) -> None:
        self.url = url
        self.title = title
        self.published_date = "2026-11-01"
        self.score = 0.8
        self.highlights = ["Software internship"]
        self.text = None


class FakeResponse:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results


class FakeSearchClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search_and_contents(self, query: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"query": query, **kwargs})
        return FakeResponse(
            [
                FakeResult("https://www.example.com/jobs/1", "Intern"),
                FakeResult("https://example.com/jobs/2", "Intern"),
            ]
        )


class TestSearch(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = Settings(
            exa_api_key="test-key",
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
            max_queries_per_run=2,
            max_results_per_query=3,
        )
        self.profile = Profile(
            role="Software Engineer",
            skills=["Python", "FastAPI"],
            location="Finland",
            languages=["English"],
            work_authorization="Eligible",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_queries_uses_profile_without_personal_defaults(self) -> None:
        queries = build_queries(self.profile, max_queries=2)

        self.assertEqual(len(queries), 2)
        self.assertTrue(any("Finland" in query for query in queries))
        self.assertIn("English", queries[0])

    def test_generated_queries_keep_the_requested_location(self) -> None:
        profile = Profile(
            role="Cyber Security",
            location="Finland",
            work_authorization="Eligible",
        )

        queries = build_queries(profile, max_queries=5, seed=42)

        self.assertTrue(all("Finland" in query for query in queries))

    def test_rotated_queries_change_with_seed(self) -> None:
        first = build_queries(self.profile, max_queries=5, seed=1)
        second = build_queries(self.profile, max_queries=5, seed=2)

        self.assertNotEqual(first, second)

    def test_search_deduplicates_by_domain_and_title(self) -> None:
        client = FakeSearchClient()
        service = SearchService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            client=client,
        )

        results = service.search_profile(self.profile)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["num_results"], 3)

    def test_second_search_uses_cache(self) -> None:
        client = FakeSearchClient()
        cache = Cache(self.config.cache_db_path)
        service = SearchService(self.config, cache=cache, client=client)

        service.search_profile(self.profile)
        results = service.search_profile(self.profile)

        self.assertTrue(all(result.from_cache for result in results))
        self.assertEqual(len(client.calls), 2)

    def test_linkedin_profile_and_personal_paths_are_blocked(self) -> None:
        service = SearchService(
            self.config,
            cache=Cache(self.config.cache_db_path),
            client=FakeSearchClient(),
        )

        self.assertTrue(service.is_blocked_url("https://linkedin.com/in/some-person"))
        self.assertTrue(service.is_blocked_url("https://example.com/blog/internships"))
        self.assertFalse(service.is_blocked_url("https://jobs.example.com/internship/python"))
