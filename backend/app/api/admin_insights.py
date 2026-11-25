"""Coordinator dashboard, student overview, LLM usage, announcements and feedback."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import Integer, cast, func, select

from app.api.deps import Coordinator, Db
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.audit import audit
from app.db.models import (
    Announcement,
    AppFeedback,
    Application,
    Job,
    JobStatus,
    JobView,
    LlmCall,
    Role,
    SavedJob,
    SearchEvent,
    StudentProfile,
    SusResponse,
    User,
)
from app.ingest.service import today
from app.llm.quota import budget_status, day_start
from app.schemas.auth import Email
from app.search.config import get_search_config

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _fortnight_ago() -> datetime:
    return datetime.now(UTC) - timedelta(days=14)


def _applications_by_stage(db: Db) -> dict[str, int]:
    query = select(Application.status, func.count()).group_by(Application.status)
    return dict(db.execute(query).tuples().all())


@router.get("/dashboard")
def dashboard(_: Coordinator, db: Db) -> dict[str, Any]:
    start = today()
    counts = select(Job.status, func.count()).group_by(Job.status)
    by_status = dict(db.execute(counts).tuples().all())
    closing = db.scalars(
        select(Job)
        .where(Job.status == JobStatus.indexed, Job.deadline.between(start, start + timedelta(7)))
        .order_by(Job.deadline)
        .limit(6)
    )
    month_ago = datetime.now(UTC) - timedelta(days=30)
    asked = func.lower(SearchEvent.query)
    gaps = db.execute(
        select(asked, func.count(), func.max(SearchEvent.result_count))
        .where(
            SearchEvent.created_at > month_ago,
            SearchEvent.query != "",
            (SearchEvent.result_count == 0) | (SearchEvent.top_similarity < get_search_config().weak_similarity),
        )
        .group_by(asked)
        .order_by(func.count().desc())
        .limit(8)
    )
    views = func.sum(JobView.count)
    viewed = db.execute(
        select(Job.id, Job.title, Job.company, views)
        .join(JobView, JobView.job_id == Job.id)
        .where(JobView.view_date >= start - timedelta(30))
        .group_by(Job.id)
        .order_by(views.desc())
        .limit(5)
    )
    saves = func.count(SavedJob.user_id)
    saved = db.execute(
        select(Job.id, Job.title, Job.company, saves)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .group_by(Job.id)
        .order_by(saves.desc())
        .limit(5)
    )
    students = select(func.count()).select_from(User).where(User.role == Role.student)

    def top(rows: Any) -> list[dict[str, Any]]:
        return [{"id": r[0], "title": r[1], "company": r[2], "count": int(r[3])} for r in rows]

    return {
        "postings_by_status": {s.value: by_status.get(s.value, 0) for s in JobStatus},
        "needs_review": db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.draft, Job.parse_meta["needs_review"].as_boolean())
        ),
        "closing_soon": [
            {"id": j.id, "title": j.title, "company": j.company, "deadline": j.deadline}
            for j in closing
        ],
        "content_gaps": [{"query": q, "searches": n, "best_results": b} for q, n, b in gaps],
        "most_viewed": top(viewed),
        "most_saved": top(saved),
        "students_total": db.scalar(students),
        "students_active": db.scalar(students.where(User.last_seen_at > _fortnight_ago())),
        "applications_by_stage": _applications_by_stage(db),
    }


@router.get("/students")
def students(_: Coordinator, db: Db) -> dict[str, Any]:
    """Counts only. Individual records need an explicit lookup, which is audited."""
    base = select(func.count()).select_from(User).where(User.role == Role.student)
    return {
        "total": db.scalar(base),
        "active": db.scalar(base.where(User.last_seen_at > _fortnight_ago())),
        "onboarded": db.scalar(base.where(User.onboarded_at.is_not(None))),
        "with_resume": db.scalar(
            base.where(User.profile.has(StudentProfile.resume_file_id.is_not(None)))
        ),
        "tracking": db.scalar(
            select(func.count(func.distinct(Application.user_id))).select_from(Application)
        ),
        "applications_by_stage": _applications_by_stage(db),
    }


class LookupIn(BaseModel):
    email: Email
    reason: str = Field(min_length=5, max_length=200)


@router.post("/students/lookup")
def lookup_student(body: LookupIn, user: Coordinator, db: Db) -> dict[str, Any]:
    student = db.scalar(select(User).where(User.email == body.email, User.role == Role.student))
    if student is None:
        raise NotFound("No student account uses that email.")
    audit(db, user.id, "student_viewed", "user", student.id, {"reason": body.reason})
    applications = db.execute(
        select(Application.status, Application.updated_at, Job.id, Job.title, Job.company)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == student.id)
        .order_by(Application.updated_at.desc())
    )
    result = {
        "full_name": student.full_name,
        "email": student.email,
        "joined": student.created_at,
        "last_seen": student.last_seen_at,
        "onboarded": student.onboarded_at is not None,
        "skills": student.profile.skills if student.profile else [],
        "applications": [
            {"status": s, "updated_at": at, "job_id": i, "title": t, "company": c}
            for s, at, i, t, c in applications
        ],
    }
    db.commit()
    return result


def _usage_summary(db: Db, *conditions: Any) -> dict[str, Any]:
    row = db.execute(
        select(
            func.count(),
            func.sum(cast(LlmCall.is_live, Integer)),
            func.sum(cast(LlmCall.cache_hit, Integer)),
            func.sum(LlmCall.input_tokens),
            func.sum(LlmCall.output_tokens),
        ).where(*conditions)
    ).one()
    live, hits = int(row[1] or 0), int(row[2] or 0)
    answerable = live + hits
    return {
        "calls": int(row[0]),
        "live_calls": live,
        "cache_hits": hits,
        "cache_hit_rate": round(hits / answerable, 3) if answerable else None,
        "input_tokens": int(row[3] or 0),
        "output_tokens": int(row[4] or 0),
    }


@router.get("/llm-usage")
def llm_usage(_: Coordinator, db: Db) -> dict[str, Any]:
    settings = get_settings()
    purposes = db.execute(
        select(
            LlmCall.purpose,
            func.count(),
            func.sum(cast(LlmCall.is_live, Integer)),
            func.sum(cast(LlmCall.cache_hit, Integer)),
            func.sum(LlmCall.input_tokens + LlmCall.output_tokens),
            func.avg(LlmCall.latency_ms),
        )
        .group_by(LlmCall.purpose)
        .order_by(func.count().desc())
    )
    recent = db.scalars(select(LlmCall).order_by(LlmCall.id.desc()).limit(20))
    return {
        "mode": "live" if settings.is_live else "mock",
        "model": settings.llm_model if settings.is_live else "mock",
        "budget": budget_status(db, settings),
        "today": _usage_summary(db, LlmCall.created_at >= day_start()),
        "all_time": _usage_summary(db),
        "by_purpose": [
            {
                "purpose": purpose,
                "calls": calls,
                "live_calls": int(live or 0),
                "cache_hits": int(hits or 0),
                "tokens": int(tokens or 0),
                "avg_latency_ms": int(latency or 0),
            }
            for purpose, calls, live, hits, tokens, latency in purposes
        ],
        "recent": [
            {
                "id": c.id,
                "purpose": c.purpose,
                "status": c.status,
                "is_live": c.is_live,
                "cache_hit": c.cache_hit,
                "latency_ms": c.latency_ms,
                "created_at": c.created_at,
            }
            for c in recent
        ],
    }


class AnnouncementIn(BaseModel):
    message: str = Field(min_length=5, max_length=300)


def _hide_all(db: Db) -> None:
    for row in db.scalars(select(Announcement).where(Announcement.is_active)):
        row.is_active = False


@router.get("/announcements")
def list_announcements(_: Coordinator, db: Db) -> list[dict[str, Any]]:
    rows = db.scalars(select(Announcement).order_by(Announcement.id.desc()).limit(30))
    return [
        {"id": a.id, "message": a.message, "is_active": a.is_active, "created_at": a.created_at}
        for a in rows
    ]


@router.post("/announcements", status_code=201)
def create_announcement(body: AnnouncementIn, user: Coordinator, db: Db) -> dict[str, int]:
    _hide_all(db)
    row = Announcement(message=body.message.strip(), created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user.id, "announced", "announcement", row.id)
    db.commit()
    return {"id": row.id}


@router.post("/announcements/{announcement_id}/{state}", status_code=204)
def toggle_announcement(
    announcement_id: int, state: Literal["show", "hide"], user: Coordinator, db: Db
) -> None:
    row = db.get(Announcement, announcement_id)
    if row is None:
        raise NotFound("That announcement does not exist.")
    if state == "show":
        _hide_all(db)
    row.is_active = state == "show"
    audit(db, user.id, f"announcement_{state}", "announcement", row.id)
    db.commit()


@router.get("/feedback")
def feedback(_: Coordinator, db: Db) -> dict[str, Any]:
    """App feedback and SUS scores, without names."""
    rows = db.scalars(select(AppFeedback).order_by(AppFeedback.id.desc()).limit(50))
    scores = list(db.scalars(select(SusResponse.score)))
    return {
        "items": [
            {
                "id": f.id,
                "category": f.category,
                "page": f.page,
                "message": f.message,
                "created_at": f.created_at,
            }
            for f in rows
        ],
        "sus": {
            "responses": len(scores),
            "mean": round(sum(scores) / len(scores), 1) if scores else None,
        },
    }
