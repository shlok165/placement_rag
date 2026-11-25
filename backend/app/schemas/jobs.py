from datetime import date, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.search.taxonomy import canonical_location, canonical_skills

JobType = Literal["internship", "full-time"]
Confidence = Literal["high", "medium", "low"]


def _url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Enter a full link that starts with https://")
    return value


def _line(value: str) -> str:
    return " ".join(value.split())


Line = Annotated[str, AfterValidator(_line)]
ApplyUrl = Annotated[str, Field(max_length=500), AfterValidator(_url)]
Money = Annotated[int, Field(ge=0, le=100_000_000)]


class JobFields(BaseModel):
    """Editable posting fields."""

    company: Line = Field("", max_length=160)
    title: Line = Field("", max_length=200)
    description: str = Field("", max_length=20_000)
    requirements: str = Field("", max_length=10_000)
    skills: Annotated[list[str], AfterValidator(canonical_skills)] = Field(
        default_factory=list, max_length=40
    )
    location: Annotated[str, AfterValidator(canonical_location)] = Field("", max_length=120)
    remote: bool = False
    job_type: JobType = "internship"
    stipend_min: Money | None = None
    stipend_max: Money | None = None
    duration_months: Annotated[int, Field(ge=1, le=36)] | None = None
    deadline: date | None = None
    apply_url: ApplyUrl = ""

    @model_validator(mode="after")
    def _ordered_stipend(self) -> "JobFields":
        low, high = self.stipend_min, self.stipend_max
        if low is not None and high is not None and low > high:
            raise ValueError("The lowest pay must not be above the highest pay.")
        return self


class ParsedJob(JobFields):
    """Parser output: the fields plus how sure the parser is about each."""

    confidence: dict[str, Confidence] = Field(default_factory=dict)


class JobCreate(JobFields):
    action: Literal["draft", "publish"] = "publish"


class JobPatch(BaseModel):
    company: Line | None = Field(None, max_length=160)
    title: Line | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=20_000)
    requirements: str | None = Field(None, max_length=10_000)
    skills: list[str] | None = Field(None, max_length=40)
    location: str | None = Field(None, max_length=120)
    remote: bool | None = None
    job_type: JobType | None = None
    stipend_min: Money | None = None
    stipend_max: Money | None = None
    duration_months: Annotated[int, Field(ge=1, le=36)] | None = None
    deadline: date | None = None
    apply_url: ApplyUrl | None = None


class PasteIn(BaseModel):
    text: str = Field(min_length=40, max_length=20_000)
    auto_publish: bool = False


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["archive", "retry", "expire"]


class JobOut(BaseModel):
    """What students see."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    title: str
    description: str
    requirements: str
    skills: list[str]
    location: str
    remote: bool
    job_type: str
    stipend_min: int | None
    stipend_max: int | None
    duration_months: int | None
    deadline: date | None
    apply_url: str
    status: str
    published_at: datetime | None


class DuplicateOut(BaseModel):
    id: int
    company: str
    title: str
    deadline: date | None
    status: str
    similarity: float


class AdminJobOut(JobOut):
    source: str
    raw_text: str | None
    parse_meta: dict[str, Any]
    auto_publish: bool
    last_error: str | None
    duplicate_of_id: int | None
    created_at: datetime
    updated_at: datetime
    indexed: bool = False
    file_name: str | None = None
    duplicates: list[DuplicateOut] = []


class AdminJobRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    title: str
    location: str
    job_type: str
    deadline: date | None
    status: str
    source: str
    last_error: str | None
    duplicate_of_id: int | None
    needs_review: bool = False
    updated_at: datetime


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class CsvRowResult(BaseModel):
    row: int
    status: Literal["created", "duplicate", "invalid"]
    message: str
    job_id: int | None = None


class CsvResult(BaseModel):
    created: int
    duplicates: int
    invalid: int
    rows: list[CsvRowResult]


class AuditOut(BaseModel):
    id: int
    action: str
    actor: str | None
    diff: dict[str, Any]
    created_at: datetime
