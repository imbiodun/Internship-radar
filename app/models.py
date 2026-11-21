from datetime import date

from pydantic import AnyHttpUrl, BaseModel, Field


class Profile(BaseModel):
    role: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    location: str = Field(min_length=1)
    languages: list[str] = Field(default_factory=list)
    work_authorization: str = Field(min_length=1)
    extra_notes: str = ""


class Posting(BaseModel):
    company: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location: str | None = None
    deadline: date | None = None
    requirements: list[str] = Field(default_factory=list)
    language_requirement: str | None = None
    eligibility_notes: str | None = None
    apply_url: AnyHttpUrl | None = None
    source_url: AnyHttpUrl
    source_snippet: str | None = None
    first_seen_at: float = 0.0
    is_new: bool = False
    page_type: str = "job_posting"
    posted_date: date | None = None
    stale_season: bool = False
    date_unverified: bool = False


class MatchResult(BaseModel):
    posting: Posting
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    posting_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sources_used: list[AnyHttpUrl] = Field(default_factory=list)


class RunStats(BaseModel):
    searched: int = 0
    deduped: int = 0
    extracted: int = 0
    extraction_failed: int = 0
    expired: int = 0
    already_seen: int = 0
    shown: int = 0
    blocked_url: int = 0
    not_a_posting: int = 0
    stale: int = 0
    date_unverified: int = 0


class SavedPosting(BaseModel):
    posting_id: str = Field(min_length=1)
    posting: Posting
    profile: Profile
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    saved_at: float
