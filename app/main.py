import time
import hashlib
from datetime import date
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.cache import Cache
from app.config import settings
from app.draft import DraftInput, DraftService
from app.extract import ExtractionService
from app.models import MatchResult, Profile, RunStats
from app.rank import RankingService
from app.search import SearchError, SearchService
from app.store import Store

app = FastAPI(title="Internship Radar")

cache = Cache(settings.cache_db_path)
store = Store(settings.cache_db_path)
_radar_requests: dict[str, float] = {}
_radar_progress: dict[str, str] = {
    "stage": "Idle",
    "detail": "Ready to search",
}


def set_progress(stage: str, detail: str) -> None:
    _radar_progress["stage"] = stage
    _radar_progress["detail"] = detail


def location_matches(profile_location: str, posting_location: str | None) -> bool:
    if posting_location is None:
        return True
    requested = profile_location.strip().lower()
    found = posting_location.strip().lower()
    if not requested or not found:
        return True
    if "remote" in found:
        return True
    if requested in found:
        return True

    location_aliases = {
        "finland": {"finland", "finland", "helsinki", "espoo", "tampere",
                    "turku", "oulu", "vantaa", "jyväskylä",
                    "järvenpää", "lappeenranta"},
        "nordics": {"finland", "sweden", "norway", "denmark", "iceland",
                    "stockholm", "oslo", "copenhagen", "reykjavik"},
        "sweden": {"sweden", "stockholm", "gothenburg", "malmo"},
        "norway": {"norway", "oslo", "bergen", "trondheim"},
        "denmark": {"denmark", "copenhagen", "aarhus"},
        "germany": {"germany", "berlin", "munich", "hamburg", "frankfurt"},
        "united kingdom": {"uk", "united kingdom", "england", "london", "manchester"},
    }
    aliases = location_aliases.get(requested)
    if aliases is not None:
        return any(alias in found for alias in aliases)
    return False


@app.middleware("http")
async def disable_api_and_ui_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


class RadarResponse(BaseModel):
    results: list[MatchResult]
    raw_source_links: list[str]
    message: str | None = None
    cached_count: int = 0
    newest_cached_age_hours: float | None = None
    provider: str | None = None
    stats: RunStats = RunStats()


class SavePostingRequest(BaseModel):
    profile: Profile
    match: MatchResult


@app.get("/")
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/static/", status_code=307)


@app.get("/api/progress")
def get_progress() -> dict[str, str]:
    return dict(_radar_progress)


@app.post("/api/radar", response_model=RadarResponse)
def run_radar(
    profile: Profile,
    request: Request,
    only_new: bool = False,
    refresh: bool = False,
) -> RadarResponse:
    set_progress("Preparing", f"Building search for {profile.role} in {profile.location}")
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
        set_progress(
            "Searching",
            f"Searching Exa for {profile.role} internships in {profile.location}",
        )
        search_results = search_service.search_profile(profile, refresh=refresh)
    except SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    deduped_results = list(
        {str(result.url): result for result in search_results}.values()
    )
    stats = RunStats(
        searched=len(search_results),
        deduped=len(deduped_results),
        blocked_url=search_service.blocked_url_count,
    )
    set_progress(
        "Filtering",
        f"Checking {len(deduped_results)} deduplicated results for {profile.location}",
    )

    extraction_service = ExtractionService(settings, cache=cache)
    postings = []
    cached_times: list[float] = []
    results_to_extract = deduped_results[: settings.max_pages_per_run]
    set_progress(
        "Extracting",
        f"Extracting structured postings from up to {len(results_to_extract)} pages",
    )
    with ThreadPoolExecutor(max_workers=5) as executor:
        extracted_results = list(
            executor.map(extraction_service.extract, results_to_extract)
        )
    for extracted in extracted_results:
        if extracted.posting is not None:
            posting = extracted.posting
            if posting.page_type != "job_posting":
                stats.not_a_posting += 1
                continue
            if posting.stale_season:
                stats.stale += 1
                continue
            postings.append(posting)
        else:
            stats.extraction_failed += 1
        if extracted.from_cache and extracted.cached_at is not None:
            cached_times.append(extracted.cached_at)

    current_postings: list = []
    already_seen = 0
    expired = 0
    stale = 0
    date_unverified = 0
    for posting in postings:
        if not location_matches(profile.location, posting.location):
            stats.not_a_posting += 1
            continue
        if posting.deadline is not None and posting.deadline < date.today():
            expired += 1
            continue
        if posting.posted_date is not None:
            age = (date.today() - posting.posted_date).days
            if age > settings.max_posting_age_days:
                stale += 1
                continue
        if posting.deadline is None and posting.posted_date is None:
            posting = posting.model_copy(
                update={"date_unverified": True}
            )
            date_unverified += 1
        seen = store.get_seen_posting(str(posting.source_url))
        if seen is not None:
            already_seen += 1
            posting = posting.model_copy(
                update={"first_seen_at": seen["first_seen_at"], "is_new": False}
            )
        else:
            posting = posting.model_copy(update={"first_seen_at": time.time(), "is_new": True})
        if only_new and not posting.is_new:
            continue
        current_postings.append(posting)

    set_progress(
        "Ranking",
        f"Ranking {len(current_postings)} postings against {profile.location}",
    )
    ranked = RankingService(settings, cache=cache).rank(profile, current_postings)
    ranked.sort(
        key=lambda match: (
            not match.posting.is_new,
            -match.score,
        )
    )
    today = time.time()
    store.record_shown_postings([match.posting for match in ranked])
    stats.extracted = len(postings)
    stats.expired = expired
    stats.stale = stats.stale + stale
    stats.date_unverified = date_unverified
    stats.already_seen = already_seen
    stats.shown = len(ranked)
    store.log_run_stats(stats)
    set_progress(
        "Complete",
        f"Returned {len(ranked)} ranked postings",
    )
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
        stats=stats,
    )


@app.get("/api/stats")
def get_stats() -> dict[str, object]:
    return {
        "counters": cache.counters(),
        "cache_only": settings.cache_only,
        "runs": store.list_run_stats(),
    }


@app.post("/api/draft")
def create_application_draft(draft_input: DraftInput):
    return DraftService(settings, cache=cache).draft(draft_input)


@app.get("/api/postings")
def list_saved_postings():
    return {"postings": store.list_saved()}


@app.post("/api/postings")
def save_posting(request: SavePostingRequest):
    posting_id = hashlib.sha256(
        str(request.match.posting.source_url).encode("utf-8")
    ).hexdigest()
    return store.save_match(posting_id, request.profile, request.match)


@app.delete("/api/postings/{posting_id}")
def delete_posting(posting_id: str):
    deleted = store.delete_saved(posting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved posting not found")
    return {"deleted": posting_id}


app.mount("/static", StaticFiles(directory="static", html=True), name="static")
