import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.cache import Cache
from app.config import settings
from app.extract import ExtractionService
from app.models import MatchResult, Profile
from app.rank import RankingService
from app.search import SearchError, SearchService

app = FastAPI(title="Internship Radar")

cache = Cache(settings.cache_db_path)
_radar_requests: dict[str, float] = {}


class RadarResponse(BaseModel):
    results: list[MatchResult]
    raw_source_links: list[str]
    message: str | None = None
    cached_count: int = 0
    newest_cached_age_hours: float | None = None
    provider: str | None = None


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Internship Radar is running"}


@app.post("/api/radar", response_model=RadarResponse)
def run_radar(profile: Profile, request: Request) -> RadarResponse:
    client_key = request.client.host if request.client else "unknown"
    now = time.time()
    previous = _radar_requests.get(client_key)
    if (
        previous is not None
        and now - previous < settings.radar_rate_limit_seconds
    ):
        raise HTTPException(
            status_code=429,
            detail="Rate limit reached. Wait before starting another radar run.",
        )
    _radar_requests[client_key] = now

    search_service = SearchService(settings, cache=cache)
    try:
        search_results = search_service.search_profile(profile)
    except SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    extraction_service = ExtractionService(settings, cache=cache)
    postings = []
    cached_times: list[float] = []
    for search_result in search_results[: settings.max_pages_per_run]:
        extracted = extraction_service.extract(search_result)
        if extracted.posting is not None:
            postings.append(extracted.posting)
        if extracted.from_cache and extracted.cached_at is not None:
            cached_times.append(extracted.cached_at)

    ranked = RankingService(settings, cache=cache).rank(profile, postings)
    provider = next(
        (
            name
            for name in ("anthropic", "gemini", "verda")
            if f"llm_call:{name}" in cache.counters()
        ),
        None,
    )
    newest_cached_age = (
        max(0.0, (time.time() - min(cached_times)) / 3600)
        if cached_times
        else None
    )
    return RadarResponse(
        results=ranked,
        raw_source_links=[result.url for result in search_results],
        message=(
            "AI ranking unavailable" if any(
                "AI ranking unavailable" in blocker
                for match in ranked
                for blocker in match.blockers
            ) else None
        ),
        cached_count=len(cached_times),
        newest_cached_age_hours=newest_cached_age,
        provider=provider,
    )


@app.get("/api/stats")
def get_stats() -> dict[str, object]:
    return {
        "counters": cache.counters(),
        "cache_only": settings.cache_only,
    }


app.mount("/static", StaticFiles(directory="static", html=True), name="static")
