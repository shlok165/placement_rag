from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.schemas.jobs import JobOut, JobType
from app.search.engine import Hit
from app.search.retrieval import Filters


class SearchFilters(BaseModel):
    job_type: JobType | None = None
    locations: list[Annotated[str, Field(max_length=120)]] = Field(
        default_factory=list, max_length=10
    )
    remote: bool | None = None
    min_stipend: int | None = Field(None, ge=0, le=100_000_000)
    closing_within_days: int | None = Field(None, ge=0, le=365)

    def to_filters(self) -> Filters:
        return Filters(**self.model_dump())


class SearchIn(BaseModel):
    query: str = Field("", max_length=300)
    filters: SearchFilters = SearchFilters()
    personalize: bool = False
    sort: Literal["relevance", "deadline", "newest", "stipend"] = "relevance"
    page: int = Field(1, ge=1, le=100)
    page_size: int = Field(20, ge=1, le=50)


class SearchHit(BaseModel):
    job: JobOut
    score: float
    breakdown: dict[str, Any] | None
    saved: bool = False
    application_status: str | None = None

    @classmethod
    def from_hit(cls, hit: Hit, saved: set[int], tracked: dict[int, str]) -> "SearchHit":
        return cls(
            job=JobOut.model_validate(hit.job),
            score=round(hit.score, 6),
            breakdown=hit.breakdown,
            saved=hit.job.id in saved,
            application_status=tracked.get(hit.job.id),
        )


class SearchOut(BaseModel):
    items: list[SearchHit]
    total: int
    page: int
    page_size: int
    personalized: bool
    # Nothing is close to the query; the UI says these are only the nearest postings.
    weak_match: bool = False
