"""Lightweight behaviour events: which postings a student saw, opened or reacted to."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, Db
from app.core.errors import NotFound
from app.db.models import EventKind, InteractionEvent, Job, JobStatus

router = APIRouter(prefix="/api", tags=["events"])

# Saves and opens are recorded by the server where they happen, and reactions have their own
# endpoint, so the browser only reports what the server cannot see.
ClientKind = Literal["impression", "apply_clicked"]
VISIBLE = (JobStatus.indexed, JobStatus.expired)


class EventIn(BaseModel):
    job_id: int = Field(ge=1)
    kind: ClientKind


class EventsIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=50)


class ReactionIn(BaseModel):
    reaction: Literal["up", "down"] | None


def record(db: Db, user_id: int, job_id: int, kind: EventKind) -> None:
    db.add(InteractionEvent(user_id=user_id, job_id=job_id, kind=kind))


def reaction(db: Db, user_id: int, job_id: int) -> Literal["up", "down"] | None:
    latest = db.scalar(
        select(InteractionEvent.kind)
        .where(
            InteractionEvent.user_id == user_id,
            InteractionEvent.job_id == job_id,
            InteractionEvent.kind.in_((EventKind.thumb_up, EventKind.thumb_down)),
        )
        .order_by(InteractionEvent.id.desc())
        .limit(1)
    )
    return None if latest is None else "up" if latest == EventKind.thumb_up else "down"


@router.post("/events", status_code=202)
def post_events(body: EventsIn, user: CurrentUser, db: Db) -> dict[str, int]:
    """Unknown or hidden postings are skipped, and repeats within one batch count once."""
    wanted = {(e.job_id, e.kind) for e in body.events}
    ids = {job_id for job_id, _ in wanted}
    visible = set(db.scalars(select(Job.id).where(Job.id.in_(ids), Job.status.in_(VISIBLE))))
    kept = sorted((j, k) for j, k in wanted if j in visible)
    for job_id, kind in kept:
        record(db, user.id, job_id, EventKind(kind))
    db.commit()
    return {"recorded": len(kept)}


@router.put("/jobs/{job_id}/reaction")
def put_reaction(job_id: int, body: ReactionIn, user: CurrentUser, db: Db) -> dict[str, str | None]:
    """Set or clear "more like this" or "fewer like this". Clearing removes the earlier ones."""
    job = db.get(Job, job_id)
    if job is None or job.status not in VISIBLE:
        raise NotFound("That posting is not available. It may have been removed.")
    db.execute(
        delete(InteractionEvent).where(
            InteractionEvent.user_id == user.id,
            InteractionEvent.job_id == job_id,
            InteractionEvent.kind.in_((EventKind.thumb_up, EventKind.thumb_down)),
        )
    )
    if body.reaction:
        kind = EventKind.thumb_up if body.reaction == "up" else EventKind.thumb_down
        record(db, user.id, job_id, kind)
    db.commit()
    return {"reaction": body.reaction}
