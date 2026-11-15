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


class MatchResult(BaseModel):
    posting: Posting
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    posting_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sources_used: list[AnyHttpUrl] = Field(default_factory=list)
