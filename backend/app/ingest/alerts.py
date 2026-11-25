"""In-app notifications for new postings and approaching deadlines. No LLM calls."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Application, Job, JobStatus, Notification, SavedJob, StudentProfile, User
from app.ingest.service import today
from app.search.matching import JobFacts, Preferences, passes_hard_filters

REMINDER_DAYS = 3


def job_facts(job: Job) -> JobFacts:
    return JobFacts(
        title=job.title,
        skills=job.skills,
        location=job.location,
        remote=job.remote,
        job_type=job.job_type,
        stipend_min=job.stipend_min,
        stipend_max=job.stipend_max,
        duration_months=job.duration_months,
    )


def _payload(job: Job) -> dict[str, object]:
    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "deadline": job.deadline.isoformat() if job.deadline else None,
    }


def _notify(db: Session, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    statement = insert(Notification).values(rows).on_conflict_do_nothing()
    return len(db.execute(statement.returning(Notification.id)).all())


def alert_matching_students(db: Session, job: Job) -> int:
    """Notify students whose profile is close to the posting and whose hard filters allow it."""
    if job.embedding is None:
        return 0
    max_distance = 1 - get_settings().alert_threshold
    profiles = db.execute(
        select(StudentProfile.user_id, StudentProfile.preferences)
        .join(User, User.id == StudentProfile.user_id)
        .where(
            User.is_active,
            StudentProfile.profile_embedding.is_not(None),
            StudentProfile.profile_embedding.cosine_distance(job.embedding) <= max_distance,
        )
    )
    facts = job_facts(job)
    rows: list[dict[str, object]] = [
        {
            "user_id": user_id,
            "type": "new_match",
            "payload": _payload(job),
            "dedupe_key": f"new_match:{user_id}:{job.id}",
        }
        for user_id, preferences in profiles
        if passes_hard_filters(facts, Preferences.from_dict(preferences))
    ]
    return _notify(db, rows)


def remind_deadlines(db: Session) -> int:
    """Remind students about saved or tracked postings that close soon."""
    start = today()
    soon = Job.deadline.between(start, start + timedelta(days=REMINDER_DAYS))
    saved = (
        select(SavedJob.user_id, Job)
        .join(Job, Job.id == SavedJob.job_id)
        .where(Job.status == JobStatus.indexed, soon)
    )
    interested = (
        select(Application.user_id, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Job.status == JobStatus.indexed, soon, Application.status == "interested")
    )
    applied = {
        (a.user_id, a.job_id)
        for a in db.scalars(select(Application).where(Application.status != "interested"))
    }
    rows: list[dict[str, object]] = []
    seen: set[tuple[int, int]] = set()
    for user_id, job in [*db.execute(saved).all(), *db.execute(interested).all()]:
        key = (user_id, job.id)
        if key in seen or key in applied:
            continue
        seen.add(key)
        rows.append(
            {
                "user_id": user_id,
                "type": "deadline_soon",
                "payload": _payload(job),
                "dedupe_key": f"deadline:{user_id}:{job.id}:{job.deadline}",
            }
        )
    return _notify(db, rows)
