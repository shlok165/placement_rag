"""Postgres-backed task queue using SELECT ... FOR UPDATE SKIP LOCKED."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import IngestTask

LOCK_TIMEOUT = timedelta(minutes=10)


def enqueue(
    db: Session, kind: str, job_id: int | None = None, payload: dict[str, Any] | None = None
) -> IngestTask:
    """Add a task to the caller's transaction, so it appears only if the change commits."""
    task = IngestTask(kind=kind, job_id=job_id, payload=payload or {}, status="queued")
    db.add(task)
    return task


def claim(db: Session) -> IngestTask | None:
    """Take the next task, including one whose worker died while holding it."""
    now = datetime.now(UTC)
    task = db.scalar(
        select(IngestTask)
        .where(
            or_(
                (IngestTask.status == "queued") & (IngestTask.run_after <= now),
                (IngestTask.status == "running") & (IngestTask.locked_at < now - LOCK_TIMEOUT),
            )
        )
        .order_by(IngestTask.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        db.rollback()
        return None
    task.status = "running"
    task.locked_at = now
    task.attempts += 1
    db.commit()
    return task


def complete(db: Session, task_id: int) -> None:
    task = db.get(IngestTask, task_id)
    if task:
        task.status = "done"
        task.locked_at = None
        task.last_error = None
        db.commit()


def fail(db: Session, task_id: int, error: str, *, retry: bool) -> None:
    task = db.get(IngestTask, task_id)
    if task is None:
        return
    task.last_error = error[:1000]
    task.locked_at = None
    if retry:
        task.status = "queued"
        task.run_after = datetime.now(UTC) + timedelta(seconds=5 * 2**task.attempts)
    else:
        task.status = "failed"
    db.commit()
