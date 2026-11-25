from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.db.models import ApplicationStatus
from app.schemas.jobs import JobOut, JobType
from app.schemas.search import SearchHit
from app.search.taxonomy import canonical_location, canonical_skills


def _clean(value: str) -> str:
    return " ".join(value.split())


def _locations(values: list[str]) -> list[str]:
    return list(dict.fromkeys(canonical_location(v) for v in values if v.strip()))


Short = Annotated[str, Field(max_length=200), AfterValidator(_clean)]
Summary = Annotated[str, Field(max_length=600), AfterValidator(_clean)]
Skills = Annotated[list[str], Field(max_length=60), AfterValidator(canonical_skills)]


class Education(BaseModel):
    degree: Short = ""
    institution: Short = ""
    year: Short = ""


class Project(BaseModel):
    title: Short = ""
    summary: Summary = ""


class Experience(BaseModel):
    role: Short = ""
    organisation: Short = ""
    summary: Summary = ""


class ParsedProfile(BaseModel):
    education: list[Education] = Field(default_factory=list, max_length=8)
    skills: Skills = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list, max_length=12)
    experience: list[Experience] = Field(default_factory=list, max_length=12)


class PreferencesIn(BaseModel):
    roles: list[Short] = Field(default_factory=list, max_length=10)
    locations: Annotated[list[Short], Field(max_length=15), AfterValidator(_locations)] = Field(
        default_factory=list
    )
    remote_ok: bool = True
    job_types: list[JobType] = Field(default_factory=list, max_length=2)
    duration: Annotated[int, Field(ge=1, le=24)] | None = None
    start_window: Short = ""
    min_stipend: Annotated[int, Field(ge=0, le=10_000_000)] | None = None


class ProfileIn(BaseModel):
    parsed_profile: ParsedProfile


class ProfileOut(BaseModel):
    skills: list[str]
    parsed_profile: ParsedProfile
    preferences: PreferencesIn
    resume_name: str | None
    resume_text_redacted: str | None
    updated_at: datetime | None


class ResumeOut(ProfileOut):
    redactions: dict[str, int]
    parsed_by: Literal["live", "cache", "mock", "local"]


class ApplicationIn(BaseModel):
    status: ApplicationStatus
    notes: str | None = Field(None, max_length=2000)


class ApplicationOut(BaseModel):
    id: int
    status: ApplicationStatus
    notes: str
    updated_at: datetime
    job: JobOut


class JobDetail(BaseModel):
    job: JobOut
    breakdown: dict[str, Any] | None
    saved: bool
    application: ApplicationOut | None
    similar: list[JobOut]


class HomeOut(BaseModel):
    recommended: list[SearchHit]
    closing_soon: list[SearchHit]
    pipeline: dict[str, int]
    unread: int
    profile_ready: bool


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class SavedSearchIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80), AfterValidator(_clean)]
    query: str = Field("", max_length=300)
    filters: dict[str, Any] = Field(default_factory=dict)


class SavedSearchOut(SavedSearchIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FeedbackIn(BaseModel):
    category: Literal["idea", "problem", "praise"] = "idea"
    message: str = Field(min_length=3, max_length=2000)
    page: str = Field("", max_length=200)


class SusIn(BaseModel):
    answers: list[Annotated[int, Field(ge=1, le=5)]] = Field(min_length=10, max_length=10)
    comment: str = Field("", max_length=1000)
