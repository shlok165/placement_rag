"""Database models."""

import enum
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384

JsonDict = dict[str, Any]


class Base(DeclarativeBase):
    type_annotation_map = {
        JsonDict: JSONB,
        list[str]: ARRAY(Text),
        list[int]: ARRAY(Integer),
        datetime: DateTime(timezone=True),
    }


class Role(enum.StrEnum):
    student = "student"
    coordinator = "coordinator"


class JobStatus(enum.StrEnum):
    draft = "draft"
    pending = "pending"
    indexed = "indexed"
    failed = "failed"
    expired = "expired"
    archived = "archived"


class ApplicationStatus(enum.StrEnum):
    interested = "interested"
    applied = "applied"
    oa = "oa"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


def _id() -> Any:
    return mapped_column(Integer, primary_key=True)


def _created(**kwargs: Any) -> Any:
    return mapped_column(server_default=func.now(), **kwargs)


def _updated() -> Any:
    return mapped_column(server_default=func.now(), onupdate=func.now())


def _user_fk(**kwargs: Any) -> Any:
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, **kwargs)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default=Role.student)
    full_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    consent_at: Mapped[datetime | None]
    onboarded_at: Mapped[datetime | None]
    last_seen_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()

    profile: Mapped["StudentProfile | None"] = relationship(back_populates="user", uselist=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = _user_fk()
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = _created()


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = _id()
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = _created()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = _id()
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class ResumeFile(Base):
    __tablename__ = "resume_files"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    path: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    resume_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_files.id", ondelete="SET NULL")
    )
    resume_text_redacted: Mapped[str | None] = mapped_column(Text)
    parsed_profile: Mapped[JsonDict] = mapped_column(default=dict, server_default=text("'{}'"))
    skills: Mapped[list[str]] = mapped_column(default=list, server_default=text("'{}'"))
    preferences: Mapped[JsonDict] = mapped_column(default=dict, server_default=text("'{}'"))
    profile_embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))
    updated_at: Mapped[datetime] = _updated()

    user: Mapped[User] = relationship(back_populates="profile")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = _id()
    company: Mapped[str] = mapped_column(String(160), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list[str]] = mapped_column(default=list, server_default=text("'{}'"))
    location: Mapped[str] = mapped_column(String(120), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    job_type: Mapped[str] = mapped_column(String(20), default="internship")
    stipend_min: Mapped[int | None]
    stipend_max: Mapped[int | None]
    duration_months: Mapped[int | None]
    deadline: Mapped[date | None] = mapped_column(Date, index=True)
    apply_url: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="form")
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.draft, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    parse_meta: Mapped[JsonDict] = mapped_column(default=dict, server_default=text("'{}'"))
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()
    tsv: Mapped[Any | None] = mapped_column(TSVECTOR)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_jobs_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_jobs_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_jobs_company", "company"),
    )


class JobFile(Base):
    __tablename__ = "job_files"

    id: Mapped[int] = _id()
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))


class IngestTask(Base):
    __tablename__ = "ingest_tasks"

    id: Mapped[int] = _id()
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[JsonDict] = mapped_column(default=dict, server_default=text("'{}'"))
    run_after: Mapped[datetime] = _created()
    locked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class ScheduledRun(Base):
    __tablename__ = "scheduled_runs"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    run_date: Mapped[date] = mapped_column(Date, primary_key=True)


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = _created()


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    name: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(String(300), default="")
    filters: Mapped[JsonDict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.interested)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = _updated()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[JsonDict] = mapped_column(default=dict)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), unique=True)
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created()


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = _id()
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    citations: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    meta: Mapped[JsonDict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()


class MessageFeedback(Base):
    __tablename__ = "message_feedback"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[str] = mapped_column(String(8))
    comment: Mapped[str] = mapped_column(String(1000), default="")
    promoted_case_id: Mapped[int | None]
    created_at: Mapped[datetime] = _created()


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[JsonDict] = mapped_column(default=dict)
    label: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = _created()
    resolved_at: Mapped[datetime | None]


class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = _user_fk()
    kind: Mapped[str] = mapped_column(String(20), default="fact")
    text: Mapped[str] = mapped_column(String(300))
    source_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = _id()
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    scope: Mapped[str] = mapped_column(String(60), default="app", index=True)
    model: Mapped[str] = mapped_column(String(120))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = _created(index=True)


class LlmCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Set when the prompt came from one person, so deleting the account clears the answer too.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(120))
    response: Mapped[JsonDict]
    created_at: Mapped[datetime] = _created()


class EvalSet(Base):
    __tablename__ = "eval_sets"

    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[int] = _id()
    set_id: Mapped[int] = mapped_column(ForeignKey("eval_sets.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    profile_snapshot: Mapped[JsonDict] = mapped_column(default=dict)
    relevant_job_ids: Mapped[list[int]] = mapped_column(default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = _id()
    set_id: Mapped[int | None] = mapped_column(ForeignKey("eval_sets.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30), default="retrieval")
    status: Mapped[str] = mapped_column(String(20), default="done")
    config: Mapped[JsonDict] = mapped_column(default=dict)
    metrics: Mapped[JsonDict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()


class SearchEvent(Base):
    __tablename__ = "search_events"

    id: Mapped[int] = _id()
    query: Mapped[str] = mapped_column(String(300))
    result_count: Mapped[int] = mapped_column(Integer)
    top_similarity: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _created(index=True)


class JobView(Base):
    __tablename__ = "job_views"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    view_date: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = _id()
    message: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _created()


class AppFeedback(Base):
    __tablename__ = "app_feedback"

    id: Mapped[int] = _id()
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    page: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(30), default="idea")
    message: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = _created()


class SusResponse(Base):
    __tablename__ = "sus_responses"

    id: Mapped[int] = _id()
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    answers: Mapped[list[int]]
    score: Mapped[float] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = _id()
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40))
    diff: Mapped[JsonDict] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_audit_entity", "entity", "entity_id"),)
