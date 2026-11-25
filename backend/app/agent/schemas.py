"""Tool arguments, the structured answer and the events sent to the browser."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ApplicationStatus
from app.schemas.jobs import JobType

JobId = Annotated[int, Field(ge=1, description="Numeric job_id from a tool result")]


class ToolArgs(BaseModel):
    # Unknown arguments are rejected, so a model can never pass a user id.
    model_config = ConfigDict(extra="forbid")


class SearchFiltersArgs(ToolArgs):
    job_type: JobType | None = None
    locations: list[str] = Field(default_factory=list, max_length=5)
    remote: bool | None = Field(None, description="true for remote postings only")
    min_stipend: int | None = Field(None, ge=0, description="rupees")
    closing_within_days: int | None = Field(None, ge=0, le=365)


class SearchJobsArgs(ToolArgs):
    """Search open postings. Results are ranked for the student."""

    query: str = Field(max_length=300, description="Topic, role, skill or company. May be empty")
    filters: SearchFiltersArgs = Field(default_factory=SearchFiltersArgs)
    k: int = Field(5, ge=1, le=8)


class GetJobArgs(ToolArgs):
    """Full details of one posting."""

    job_id: JobId


class GetProfileArgs(ToolArgs):
    """The student's own skills, preferences and background."""


class PreferenceChanges(ToolArgs):
    roles: list[str] | None = Field(None, max_length=10)
    locations: list[str] | None = Field(None, max_length=15)
    remote_ok: bool | None = None
    job_types: list[JobType] | None = Field(None, max_length=2)
    duration: int | None = Field(None, ge=1, le=24, description="months")
    start_window: str | None = Field(None, max_length=200)
    min_stipend: int | None = Field(None, ge=0, le=10_000_000)


class UpdatePreferencesArgs(ToolArgs):
    """Propose a change to saved preferences. The student confirms it on screen."""

    changes: PreferenceChanges


class SaveJobArgs(ToolArgs):
    """Propose saving a posting. The student confirms it on screen."""

    job_id: JobId


class TrackApplicationArgs(ToolArgs):
    """Propose tracking an application at a stage. The student confirms it on screen."""

    job_id: JobId
    status: ApplicationStatus
    notes: str = Field("", max_length=500)


class ListDeadlinesArgs(ToolArgs):
    """Postings that close soon, with those the student saved or tracks first."""

    within_days: int = Field(7, ge=0, le=90)


class CompareJobsArgs(ToolArgs):
    """Compare two to four postings side by side."""

    job_ids: list[JobId] = Field(min_length=2, max_length=4)


class ExplainFitArgs(ToolArgs):
    """Score breakdown of how one posting fits the student's profile."""

    job_id: JobId


class SkillGapArgs(ToolArgs):
    """Required skills the student has and lacks for one posting."""

    job_id: JobId


class FinalAnswerArgs(ToolArgs):
    """Finish the turn with the answer shown to the student."""

    answer_markdown: str = Field(
        min_length=1,
        max_length=4000,
        description="Short answer. Mark every posting you mention with [#job_id]",
    )
    cited_job_ids: list[int] = Field(default_factory=list, max_length=12)
    suggested_followups: list[Annotated[str, Field(max_length=120)]] = Field(
        default_factory=list, max_length=3
    )


class Citation(BaseModel):
    job_id: int
    title: str
    company: str


class PendingActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Literal["save_job", "track_application", "update_preferences", "remember"]
    label: str
    payload: dict[str, Any]
    status: Literal["pending", "confirmed", "rejected"]


class AgentAnswer(BaseModel):
    """Structured result of a turn."""

    answer_markdown: str
    citations: list[Citation] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    pending_actions: list[PendingActionOut] = Field(default_factory=list)


class ToolTrace(BaseModel):
    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str = ""


class MessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    pending_actions: list[PendingActionOut] = Field(default_factory=list)
    notice: str | None = None
    stopped: bool = False
    feedback: Literal["up", "down"] | None = None
    created_at: datetime


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    updated_at: datetime


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    text: str
    created_at: datetime


class ProposedFact(BaseModel):
    kind: Literal["preference", "fact"]
    text: str = Field(min_length=3, max_length=200)


class ProposedFacts(BaseModel):
    facts: list[ProposedFact] = Field(default_factory=list, max_length=3)
