"""Student-facing postings, saves, applications, notifications and feedback."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import CurrentUser, Db
from app.api.events import reaction, record
from app.api.search import annotate
from app.core.errors import AppError, NotFound
from app.db.models import (
    Announcement,
    AppFeedback,
    Application,
    EventKind,
    InteractionEvent,
    Job,
    JobStatus,
    JobView,
    Notification,
    SavedJob,
    SavedSearch,
    SusResponse,
)
from app.ingest.service import today
from app.schemas.jobs import JobOut
from app.schemas.search import SearchHit
from app.schemas.student import (
    ApplicationIn,
    ApplicationOut,
    FeedbackIn,
    HomeOut,
    JobDetail,
    NotificationOut,
    SavedSearchIn,
    SavedSearchOut,
    SusIn,
)
from app.search.config import get_search_config
from app.search.engine import Hit, search, similar_jobs
from app.search.profiles import load_ranking_profile
from app.search.ranking import score_job
from app.search.retrieval import Filters

router = APIRouter(prefix="/api", tags=["student"])

VISIBLE = (JobStatus.indexed, JobStatus.expired)
MAX_SAVED_SEARCHES = 20


def visible_job(db: Db, job_id: int) -> Job:
    """Drafts and archived postings do not exist as far as students are concerned."""
    job = db.get(Job, job_id)
    if job is None or job.status not in VISIBLE:
        raise NotFound("That posting is not available. It may have been removed.")
    return job


# ------------------------------------------------------------------ home and jobs


@router.get("/home", response_model=HomeOut)
def home(user: CurrentUser, db: Db) -> HomeOut:
    profile = load_ranking_profile(db, user.id)
    applied = set(db.scalars(select(Application.job_id).where(Application.user_id == user.id)))
    exclude = Filters(exclude_ids=sorted(applied))
    recommended = search(db, "", exclude, profile=profile, limit=6)
    soon = Filters(exclude_ids=sorted(applied), closing_within_days=7)
    closing = search(db, "", soon, profile=profile, sort="deadline", limit=5)
    stages = select(Application.status, func.count()).where(Application.user_id == user.id)
    unread = select(func.count()).select_from(Notification)
    return HomeOut(
        recommended=annotate(db, user, recommended.hits),
        closing_soon=annotate(db, user, closing.hits),
        pipeline=dict(db.execute(stages.group_by(Application.status)).tuples().all()),
        unread=db.scalar(
            unread.where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0,
        profile_ready=not profile.is_empty,
    )


@router.get("/jobs/{job_id}", response_model=JobDetail)
def job_detail(job_id: int, user: CurrentUser, db: Db) -> JobDetail:
    job = visible_job(db, job_id)
    db.execute(
        insert(JobView)
        .values(job_id=job.id, view_date=today(), count=1)
        .on_conflict_do_update(
            index_elements=["job_id", "view_date"], set_={"count": JobView.count + 1}
        )
    )
    record(db, user.id, job.id, EventKind.open)
    profile = load_ranking_profile(db, user.id)
    breakdown = None
    if not profile.is_empty:
        breakdown = score_job(job, profile, get_search_config().rerank, today())
    saved = db.get(SavedJob, (user.id, job.id)) is not None
    application = db.scalar(
        select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
    )
    similar = similar_jobs(db, job)
    db.commit()
    return JobDetail(
        job=JobOut.model_validate(job),
        breakdown=breakdown,
        saved=saved,
        application=_application(application, job) if application else None,
        similar=[JobOut.model_validate(j) for j in similar],
        reaction=reaction(db, user.id, job.id),
    )


# ------------------------------------------------------------------ saved


@router.get("/saved", response_model=list[SearchHit])
def list_saved(user: CurrentUser, db: Db) -> list[SearchHit]:
    jobs = db.scalars(
        select(Job)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .where(SavedJob.user_id == user.id, Job.status.in_(VISIBLE))
        .order_by(SavedJob.created_at.desc())
    )
    profile = load_ranking_profile(db, user.id)
    config = get_search_config().rerank
    hits = []
    for job in jobs:
        detail = None if profile.is_empty else score_job(job, profile, config, today())
        hits.append(Hit(job, detail["score"] if detail else 0.0, detail))
    return annotate(db, user, hits)


def save(db: Db, user_id: int, job_id: int) -> None:
    statement = insert(SavedJob).values(user_id=user_id, job_id=job_id)
    # RETURNING yields a row only when the save is new, so a repeat records no second event.
    if db.scalar(statement.on_conflict_do_nothing().returning(SavedJob.job_id)) is not None:
        record(db, user_id, job_id, EventKind.save)
    db.commit()


@router.put("/saved/{job_id}", status_code=204)
def save_job(job_id: int, user: CurrentUser, db: Db) -> None:
    visible_job(db, job_id)
    save(db, user.id, job_id)


@router.delete("/saved/{job_id}", status_code=204)
def unsave_job(job_id: int, user: CurrentUser, db: Db) -> None:
    db.execute(delete(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id))
    # An undone save no longer says anything about taste.
    db.execute(
        delete(InteractionEvent).where(
            InteractionEvent.user_id == user.id,
            InteractionEvent.job_id == job_id,
            InteractionEvent.kind == EventKind.save,
        )
    )
    db.commit()


# ------------------------------------------------------------------ applications


def _application(row: Application, job: Job) -> ApplicationOut:
    return ApplicationOut(
        id=row.id,
        status=row.status,
        notes=row.notes,
        updated_at=row.updated_at,
        job=JobOut.model_validate(job),
    )


def track(db: Db, user_id: int, job_id: int, status: str, notes: str | None) -> Application:
    row = db.scalar(
        select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
    )
    if row is None:
        row = Application(user_id=user_id, job_id=job_id, notes="")
        db.add(row)
    row.status = status
    if notes is not None:
        row.notes = notes
    db.commit()
    db.refresh(row)
    return row


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(user: CurrentUser, db: Db) -> list[ApplicationOut]:
    rows = db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    )
    return [_application(row, job) for row, job in rows]


@router.put("/applications/{job_id}", response_model=ApplicationOut)
def put_application(job_id: int, body: ApplicationIn, user: CurrentUser, db: Db) -> ApplicationOut:
    # Tracking stays possible after a posting is archived, so past applications can be updated.
    job = db.get(Job, job_id)
    tracked = db.scalar(
        select(Application.id).where(Application.user_id == user.id, Application.job_id == job_id)
    )
    if job is None or (tracked is None and job.status not in VISIBLE):
        raise NotFound("That posting is not available. It may have been removed.")
    return _application(track(db, user.id, job_id, body.status, body.notes), job)


@router.delete("/applications/{job_id}", status_code=204)
def delete_application(job_id: int, user: CurrentUser, db: Db) -> None:
    db.execute(
        delete(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    )
    db.commit()


# ------------------------------------------------------------------ notifications


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(user: CurrentUser, db: Db) -> Sequence[Notification]:
    return db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(50)
    ).all()


@router.get("/notifications/unread")
def unread_count(user: CurrentUser, db: Db) -> dict[str, int]:
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return {"unread": count or 0}


@router.post("/notifications/read", status_code=204)
def mark_all_read(user: CurrentUser, db: Db) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, user: CurrentUser, db: Db) -> None:
    db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .values(read_at=datetime.now(UTC))
    )
    db.commit()


# ------------------------------------------------------------------ saved searches


@router.get("/saved-searches", response_model=list[SavedSearchOut])
def list_saved_searches(user: CurrentUser, db: Db) -> Sequence[SavedSearch]:
    query = select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.id)
    return db.scalars(query).all()


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=201)
def create_saved_search(body: SavedSearchIn, user: CurrentUser, db: Db) -> SavedSearch:
    count = select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user.id)
    if (db.scalar(count) or 0) >= MAX_SAVED_SEARCHES:
        raise AppError(f"You can keep {MAX_SAVED_SEARCHES} saved searches. Remove one first.")
    row = SavedSearch(user_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    return row


@router.delete("/saved-searches/{search_id}", status_code=204)
def delete_saved_search(search_id: int, user: CurrentUser, db: Db) -> None:
    db.execute(
        delete(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user.id)
    )
    db.commit()


# ------------------------------------------------------------------ announcements, feedback


@router.get("/announcement")
def announcement(_: CurrentUser, db: Db) -> dict[str, Any]:
    row = db.scalar(
        select(Announcement).where(Announcement.is_active).order_by(Announcement.id.desc())
    )
    return {"id": row.id, "message": row.message} if row else {"id": None, "message": None}


@router.post("/feedback", status_code=201)
def send_feedback(body: FeedbackIn, user: CurrentUser, db: Db) -> dict[str, bool]:
    db.add(AppFeedback(user_id=user.id, **body.model_dump()))
    db.commit()
    return {"received": True}


def sus_score(answers: list[int]) -> float:
    """System Usability Scale: odd items score answer-1, even items 5-answer, times 2.5."""
    odd = sum(a - 1 for a in answers[0::2])
    even = sum(5 - a for a in answers[1::2])
    return (odd + even) * 2.5


@router.post("/sus", status_code=201)
def submit_sus(body: SusIn, user: CurrentUser, db: Db) -> dict[str, float]:
    score = sus_score(body.answers)
    existing = db.scalar(select(SusResponse).where(SusResponse.user_id == user.id))
    row = existing or SusResponse(user_id=user.id)
    row.answers, row.score, row.comment = body.answers, score, body.comment
    db.add(row)
    db.commit()
    return {"score": score}
