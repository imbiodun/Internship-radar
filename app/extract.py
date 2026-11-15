import hashlib
from collections.abc import Callable
from typing import Any

from pydantic import AnyHttpUrl, BaseModel

from app.cache import Cache
from app.config import Settings, settings
from app.llm import LLMError, complete_json
from app.models import Posting
from app.search import SearchResult

MAX_SOURCE_TEXT = 12_000


class ExtractionResult(BaseModel):
    source_url: AnyHttpUrl
    posting: Posting | None = None
    error: str | None = None
    from_cache: bool = False
    cached_at: float | None = None


CompleteJson = Callable[[str, type[Posting], str], Posting]


class ExtractionService:
    def __init__(
        self,
        config: Settings,
        cache: Cache | None = None,
        complete: CompleteJson = complete_json,
    ) -> None:
        self.config = config
        self.cache = cache or Cache(config.cache_db_path)
        self.complete = complete

    def extract(self, result: SearchResult) -> ExtractionResult:
        source_text = self._source_text(result)
        content_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        cache_key = Cache.key_for(
            {
                "schema_version": "posting-extraction-v1",
                "source_url": result.url,
                "content_hash": content_hash,
            }
        )
        cached = self.cache.get(cache_key, self.config.extraction_ttl_seconds)
        if cached is not None:
            return ExtractionResult(
                source_url=result.url,
                posting=Posting.model_validate(cached.value["posting"]),
                from_cache=True,
                cached_at=cached.created_at,
            )
        if self.config.cache_only:
            return ExtractionResult(
                source_url=result.url,
                error="Posting extraction not cached and CACHE_ONLY=true",
            )

        prompt = self._prompt(result.url, source_text)
        try:
            posting = self.complete(prompt, Posting, "cheap")
        except LLMError as exc:
            return ExtractionResult(source_url=result.url, error=str(exc))

        self.cache.set(
            cache_key,
            "llm_extraction",
            {"source_url": result.url, "posting": posting.model_dump(mode="json")},
        )
        return ExtractionResult(source_url=result.url, posting=posting)

    @staticmethod
    def _source_text(result: SearchResult) -> str:
        content = "\n".join(result.highlights).strip()
        if not content:
            content = (result.text or "").strip()
        return content[:MAX_SOURCE_TEXT]

    @staticmethod
    def _prompt(source_url: str, source_text: str) -> str:
        return f"""
Extract a single internship posting from the provided page evidence.
Return only JSON matching the requested schema.
Use null when a nullable field is not explicitly supported by the evidence.
Never infer a deadline, language requirement, eligibility rule, company, or title.
The source_url must be exactly the provided URL.

Source URL: {source_url}
Page evidence:
{source_text}
""".strip()


def extract_posting(result: SearchResult) -> ExtractionResult:
    return ExtractionService(settings).extract(result)
