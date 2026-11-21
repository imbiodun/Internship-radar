from datetime import date, timedelta
import random
import time
from typing import Any, Protocol
from urllib.parse import urlsplit

from exa_py import Exa
from pydantic import BaseModel, Field

from app.cache import Cache
from app.config import Settings, settings
from app.models import Profile


class SearchError(RuntimeError):
    """Raised when Exa search cannot return results."""


class SearchClient(Protocol):
    def search_and_contents(self, query: str, **kwargs: Any) -> Any:
        ...


class SearchResult(BaseModel):
    url: str
    title: str | None = None
    published_date: str | None = None
    score: float | None = None
    highlights: list[str] = Field(default_factory=list)
    text: str | None = None
    from_cache: bool = False
    cached_at: float | None = None


def build_queries(
    profile: Profile,
    max_queries: int = 5,
    seed: int | None = None,
) -> list[str]:
    rng = random.Random(seed if seed is not None else int(time.time()))
    language_text = " ".join(profile.languages)
    today = date.today()
    next_season_year = today.year + (0 if today.month < 7 else 1)
    role_synonyms = [
        profile.role,
        "software engineer",
        "backend",
        "full-stack",
        "trainee",
        "thesis position",
    ]
    location = profile.location.strip()
    axes = [
        f"{role} internship {location} summer {next_season_year}"
        for role in role_synonyms
    ]
    rng.shuffle(axes)
    if language_text:
        axes = [f"{query} {language_text}" for query in axes]
    if profile.skills:
        axes.append(
            f"{profile.role} internship {' '.join(profile.skills[:3])} {profile.location}"
        )
    return list(dict.fromkeys(axes))[:max_queries]


class SearchService:
    def __init__(
        self,
        config: Settings,
        cache: Cache | None = None,
        client: SearchClient | None = None,
    ) -> None:
        self.config = config
        self.cache = cache or Cache(config.cache_db_path)
        self.client = client
        self.blocked_url_count = 0

    def search_profile(
        self,
        profile: Profile,
        refresh: bool = False,
    ) -> list[SearchResult]:
        if self.config.cache_only:
            return self._search_queries(profile, client=None)
        if not self.config.exa_api_key:
            raise SearchError("EXA_API_KEY is not configured")
        client = self.client or Exa(self.config.exa_api_key)
        return self._search_queries(profile, client=client, refresh=refresh)

    def _search_queries(
        self,
        profile: Profile,
        client: SearchClient | None,
        refresh: bool = False,
    ) -> list[SearchResult]:
        all_results: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        self.blocked_url_count = 0
        published_after = (
            date.today() - timedelta(days=self.config.search_window_days)
        ).isoformat()
        run_seed = int(time.time())
        for index, query in enumerate(
            build_queries(profile, self.config.max_queries_per_run, seed=run_seed)
        ):
            parameters = {
                "query": query,
                "num_results": self.config.max_results_per_query,
                "start_published_date": published_after,
                "type": "neural",
                "highlights": {"max_characters": 2000},
                "exclude_domains": list(self.config.blocked_domains),
            }
            if index < 2:
                parameters["include_domains"] = list(self.config.include_domains)
            cache_key = Cache.key_for({"schema_version": "exa-search-v2", **parameters})
            cached = (
                None
                if refresh
                else self.cache.get(cache_key, self.config.exa_search_ttl_seconds)
            )
            if cached is not None:
                results = [
                    SearchResult.model_validate(
                        {**item, "from_cache": True, "cached_at": cached.created_at}
                    )
                    for item in cached.value["results"]
                ]
            else:
                if client is None:
                    raise SearchError(f"Search results not cached for query: {query}")
                try:
                    response = client.search_and_contents(**parameters)
                    results = [self._result_from_sdk(item) for item in response.results]
                except Exception as exc:
                    raise SearchError(
                        f"Exa search failed: {type(exc).__name__}"
                    ) from exc
                self.cache.record_event("exa_call", "exa")
                self.cache.set(
                    cache_key,
                    "exa_search",
                    {"query": query, "results": [item.model_dump() for item in results]},
                )

            for result in results:
                if self.is_blocked_url(result.url):
                    self.blocked_url_count += 1
                    continue
                identity = self._identity(result)
                if identity not in seen:
                    seen.add(identity)
                    all_results.append(result)
        return all_results

    def is_blocked_url(self, url: str) -> bool:
        parsed = urlsplit(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        if any(
            domain == blocked or domain.endswith(f".{blocked}")
            for blocked in self.config.blocked_domains
        ):
            return True
        return any(pattern in path for pattern in self.config.blocked_url_patterns)

    @staticmethod
    def _identity(result: SearchResult) -> tuple[str, str]:
        domain = urlsplit(result.url).netloc.lower().removeprefix("www.")
        title = (result.title or "").strip().lower()
        return domain, title

    @staticmethod
    def _result_from_sdk(result: Any) -> SearchResult:
        return SearchResult(
            url=result.url,
            title=result.title,
            published_date=result.published_date,
            score=result.score,
            highlights=result.highlights or [],
            text=result.text,
        )


def search_profile(profile: Profile) -> list[SearchResult]:
    return SearchService(settings).search_profile(profile)
