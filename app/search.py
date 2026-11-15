from datetime import date, timedelta
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


def build_queries(profile: Profile, max_queries: int = 5) -> list[str]:
    language_text = " ".join(profile.languages)
    base = f"{profile.role} internship {profile.location}".strip()
    queries = [f"{base} {language_text}".strip()]
    if profile.skills:
        queries.append(f"{profile.role} internship {profile.skills[0]} {profile.location}")
    if len(profile.skills) > 1:
        queries.append(
            f"{profile.role} internship {' '.join(profile.skills[:3])} {profile.location}"
        )
    queries.append(f"student {profile.role} internship {profile.location}")
    return list(dict.fromkeys(queries))[:max_queries]


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

    def search_profile(self, profile: Profile) -> list[SearchResult]:
        if self.config.cache_only:
            return self._search_queries(profile, client=None)
        if not self.config.exa_api_key:
            raise SearchError("EXA_API_KEY is not configured")
        client = self.client or Exa(self.config.exa_api_key)
        return self._search_queries(profile, client=client)

    def _search_queries(
        self, profile: Profile, client: SearchClient | None
    ) -> list[SearchResult]:
        all_results: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        published_after = (date.today() - timedelta(days=183)).isoformat()
        for query in build_queries(profile, self.config.max_queries_per_run):
            parameters = {
                "query": query,
                "num_results": self.config.max_results_per_query,
                "start_published_date": published_after,
                "type": "neural",
                "highlights": {"max_characters": 2000},
            }
            cache_key = Cache.key_for({"schema_version": "exa-search-v1", **parameters})
            cached = self.cache.get(cache_key, self.config.exa_search_ttl_seconds)
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
                identity = self._identity(result)
                if identity not in seen:
                    seen.add(identity)
                    all_results.append(result)
        return all_results

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
