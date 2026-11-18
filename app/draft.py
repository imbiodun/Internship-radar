from collections.abc import Callable

from pydantic import BaseModel

from app.cache import Cache
from app.config import Settings, settings
from app.llm import LLMError, complete_text
from app.models import Draft, Posting, Profile


class DraftInput(BaseModel):
    profile: Profile
    posting: Posting
    posting_id: str


CompleteText = Callable[[str, str], str]


class DraftService:
    def __init__(
        self,
        config: Settings,
        cache: Cache | None = None,
        complete: CompleteText = complete_text,
    ) -> None:
        self.config = config
        self.cache = cache or Cache(config.cache_db_path)
        self.complete = complete

    def draft(self, draft_input: DraftInput) -> Draft:
        profile = draft_input.profile
        posting = draft_input.posting
        cache_key = Cache.key_for(
            {
                "schema_version": "draft-v1",
                "posting_id": draft_input.posting_id,
                "profile": profile.model_dump(mode="json"),
                "posting": posting.model_dump(mode="json"),
            }
        )
        cached = self.cache.get(cache_key, self.config.draft_ttl_seconds)
        if cached is not None:
            return Draft.model_validate(cached.value)

        if self.config.cache_only:
            return Draft(
                posting_id=draft_input.posting_id,
                text="Draft unavailable: the result is not cached and CACHE_ONLY=true.",
                sources_used=[posting.source_url],
            )

        prompt = self._prompt(profile, posting)
        try:
            text = self.complete(prompt, "strong").strip()
            if not text:
                raise LLMError("Provider returned an empty draft")
        except LLMError:
            text = (
                "Draft unavailable because AI providers could not be reached. "
                "Review the source posting before writing a tailored application."
            )

        draft = Draft(
            posting_id=draft_input.posting_id,
            text=text,
            sources_used=[posting.source_url],
        )
        self.cache.set(cache_key, "llm_draft", draft.model_dump(mode="json"))
        return draft

    @staticmethod
    def _prompt(profile: Profile, posting: Posting) -> str:
        return f"""
Write a short, tailored application opening paragraph of 80 to 120 words.
Use only facts explicitly present in the candidate profile and posting below.
Do not invent experience, skills, eligibility, location, or company details.
Do not claim that a fact has been verified.

Candidate profile:
{profile.model_dump_json()}

Posting:
{posting.model_dump_json()}
""".strip()


def create_draft(draft_input: DraftInput) -> Draft:
    return DraftService(settings).draft(draft_input)
