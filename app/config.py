import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    exa_api_key: str | None
    anthropic_api_key: str | None
    gemini_api_key: str | None
    gemini_base_url: str | None
    gemini_model: str | None
    verda_api_key: str | None
    verda_base_url: str | None
    verda_model: str | None
    llm_chain: tuple[str, ...]
    anthropic_cheap_model: str
    anthropic_strong_model: str
    cache_only: bool
    cache_db_path: str
    exa_search_ttl_seconds: int = 24 * 60 * 60
    exa_contents_ttl_seconds: int = 7 * 24 * 60 * 60
    extraction_ttl_seconds: int = 7 * 24 * 60 * 60
    rank_ttl_seconds: int = 24 * 60 * 60
    draft_ttl_seconds: int = 24 * 60 * 60
    max_queries_per_run: int = 5
    max_results_per_query: int = 10
    max_pages_per_run: int = 10
    radar_rate_limit_seconds: int = 30
    search_window_days: int = 45
    max_posting_age_days: int = 120
    include_domains: tuple[str, ...] = (
        "greenhouse.io",
        "lever.co",
        "workable.com",
        "teamtailor.com",
        "duunitori.fi",
    )
    blocked_domains: tuple[str, ...] = (
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "reddit.com",
        "medium.com",
    )
    blocked_url_patterns: tuple[str, ...] = (
        "/in/",
        "/pub/",
        "/posts/",
        "/post/",
        "/feed/",
        "/company/",
        "/article/",
        "/blog/",
        "/news/",
        "/profile/",
    )


def load_settings() -> Settings:
    return Settings(
        exa_api_key=os.getenv("EXA_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_base_url=os.getenv("GEMINI_BASE_URL"),
        gemini_model=os.getenv("GEMINI_MODEL"),
        verda_api_key=os.getenv("VERDA_API_KEY"),
        verda_base_url=os.getenv("VERDA_BASE_URL"),
        verda_model=os.getenv("VERDA_MODEL"),
        llm_chain=_env_list("LLM_CHAIN", ("anthropic", "gemini", "verda")),
        anthropic_cheap_model=os.getenv(
            "ANTHROPIC_CHEAP_MODEL", "claude-haiku-5-5"
        ),
        anthropic_strong_model=os.getenv(
            "ANTHROPIC_STRONG_MODEL", "claude-sonnet-5-5"
        ),
        cache_only=_env_flag("CACHE_ONLY"),
        cache_db_path=os.getenv("CACHE_DB_PATH", "radar.db"),
        search_window_days=int(os.getenv("SEARCH_WINDOW_DAYS", "45")),
        max_posting_age_days=int(os.getenv("MAX_POSTING_AGE_DAYS", "120")),
    )


settings = load_settings()
