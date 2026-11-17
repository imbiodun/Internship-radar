from collections.abc import Callable
from datetime import date
from typing import TypeVar

from pydantic import BaseModel, Field

from app.cache import Cache
from app.config import Settings, settings
from app.llm import LLMError, complete_json
from app.models import MatchResult, Posting, Profile

ModelT = TypeVar("ModelT", bound=BaseModel)


class RankedItem(BaseModel):
    index: int = Field(ge=0)
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class RankedBatch(BaseModel):
    results: list[RankedItem] = Field(default_factory=list)


CompleteJson = Callable[[str, type[RankedBatch], str], RankedBatch]


class RankingService:
    def __init__(
        self,
        config: Settings,
        cache: Cache | None = None,
        complete: CompleteJson = complete_json,
    ) -> None:
        self.config = config
        self.cache = cache or Cache(config.cache_db_path)
        self.complete = complete

    def rank(self, profile: Profile, postings: list[Posting]) -> list[MatchResult]:
        if not postings:
            return []
        cache_key = Cache.key_for(
            {
                "schema_version": "posting-rank-v1",
                "profile": profile.model_dump(mode="json"),
                "postings": [posting.model_dump(mode="json") for posting in postings],
            }
        )
        cached = self.cache.get(cache_key, self.config.rank_ttl_seconds)
        if cached is not None:
            return self._with_current_blockers(
                [MatchResult.model_validate(item) for item in cached.value["results"]]
            )

        if self.config.cache_only:
            return self._unranked(postings, "AI ranking unavailable: result not cached")

        prompt = self._prompt(profile, postings)
        try:
            ranked = self.complete(prompt, RankedBatch, "strong")
            results = self._merge_rankings(postings, ranked)
        except LLMError:
            results = self._unranked(postings, "AI ranking unavailable")

        self.cache.set(
            cache_key,
            "llm_rank",
            {"results": [result.model_dump(mode="json") for result in results]},
        )
        return self._with_current_blockers(results)

    @staticmethod
    def _prompt(profile: Profile, postings: list[Posting]) -> str:
        return f"""
Rank every internship posting against the candidate profile in one batch.
Return one result per posting using its zero-based index.
Score from 0 to 100. Explain the score with concise reasons.
Use blockers for explicit language, eligibility, authorization, or deadline conflicts.
Never infer facts not present in the profile or posting.

Profile:
{profile.model_dump_json()}

Postings:
{[posting.model_dump(mode="json") for posting in postings]}
""".strip()

    @staticmethod
    def _merge_rankings(
        postings: list[Posting], ranked: RankedBatch
    ) -> list[MatchResult]:
        by_index = {item.index: item for item in ranked.results}
        return [
            MatchResult(
                posting=posting,
                score=by_index[index].score if index in by_index else 0,
                reasons=(
                    by_index[index].reasons
                    if index in by_index
                    else ["No ranking returned for this posting"]
                ),
                blockers=by_index[index].blockers if index in by_index else [],
            )
            for index, posting in enumerate(postings)
        ]

    @staticmethod
    def _unranked(postings: list[Posting], reason: str) -> list[MatchResult]:
        return [
            MatchResult(posting=posting, score=0, reasons=[], blockers=[reason])
            for posting in postings
        ]

    @staticmethod
    def _with_current_blockers(results: list[MatchResult]) -> list[MatchResult]:
        today = date.today()
        updated: list[MatchResult] = []
        for result in results:
            blockers = list(result.blockers)
            if result.posting.deadline and result.posting.deadline < today:
                message = "Application deadline has passed"
                if message not in blockers:
                    blockers.append(message)
            updated.append(result.model_copy(update={"blockers": blockers}))
        return sorted(updated, key=lambda result: result.score, reverse=True)


def rank_postings(profile: Profile, postings: list[Posting]) -> list[MatchResult]:
    return RankingService(settings).rank(profile, postings)
