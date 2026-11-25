"""Work done by the worker container."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.storage import get_storage
from app.core.uploads import extract_text
from app.db.audit import audit
from app.db.models import IngestTask, Job, JobFile, JobStatus, ScheduledRun
from app.ingest import alerts, queue
from app.ingest.duplicates import find_similar
from app.ingest.indexing import index_job
from app.ingest.parser import parse_job_text
from app.ingest.service import EDITABLE, publish_problems, today
from app.llm.client import get_llm

logger = logging.getLogger("app.worker")


def _job(db: Session, task: IngestTask) -> Job | None:
    return db.get(Job, task.job_id) if task.job_id else None


def run_parse(db: Session, task: IngestTask) -> None:
    job = _job(db, task)
    if job is None:
        return
    if job.raw_text is None:
        file = db.scalar(select(JobFile).where(JobFile.job_id == job.id))
        if file is None:
            raise AppError("The uploaded file is missing. Upload it again.", code="file_missing")
        job.raw_text = extract_text(get_storage().read(file.path), file.mime)
        db.commit()
    parsed, mode = parse_job_text(get_llm(), job.raw_text, job.created_by)
    for field in EDITABLE:
        setattr(job, field, getattr(parsed, field))
    similar = find_similar(db, job.company, job.title, job.deadline, exclude_id=job.id)
    job.duplicate_of_id = similar[0].id if similar else None
    low = [f for f, level in parsed.confidence.items() if level == "low"]
    job.parse_meta = {"confidence": parsed.confidence, "parsed_by": mode, "low_confidence": low}
    if job.auto_publish and not similar and not publish_problems(job):
        job.parse_meta = {**job.parse_meta, "needs_review": False}
        index_job(job)
        alerts.alert_matching_students(db, job)
        audit(db, job.created_by, "published", "job", job.id, {"auto": True})
    else:
        job.parse_meta = {**job.parse_meta, "needs_review": True}
        job.status = JobStatus.draft
    db.commit()


def run_index(db: Session, task: IngestTask) -> None:
    job = _job(db, task)
    if job is None or job.status != JobStatus.pending:
        return
    index_job(job)
    if task.payload.get("alerts", True):
        alerts.alert_matching_students(db, job)
    db.commit()


def run_expire(db: Session, _: IngestTask) -> None:
    expired = db.execute(
        update(Job)
        .where(Job.status == JobStatus.indexed, Job.deadline < today())
        .values(
            status=JobStatus.expired,
            parse_meta=Job.parse_meta.op("||")({"previous_status": "indexed"}),
        )
        .returning(Job.id)
    ).scalars()
    for job_id in expired:
        audit(db, None, "expired", "job", job_id, {"by": "nightly task"})
    db.commit()


def run_reminders(db: Session, _: IngestTask) -> None:
    alerts.remind_deadlines(db)
    db.commit()


HANDLERS = {
    "parse": run_parse,
    "index": run_index,
    "expire": run_expire,
    "reminders": run_reminders,
}


def process_one(db: Session) -> bool:
    """Run the next task. Returns False when the queue is empty."""
    task = queue.claim(db)
    if task is None:
        return False
    task_id, job_id, kind = task.id, task.job_id, task.kind
    try:
        HANDLERS[kind](db, task)
    except Exception as exc:
        db.rollback()
        # An AppError explains a problem with the input, so trying again cannot help.
        permanent = isinstance(exc, AppError) and exc.status_code < 500
        retry = not permanent and task.attempts < get_settings().ingest_max_attempts
        message = exc.message if isinstance(exc, AppError) else "Processing stopped unexpectedly."
        queue.fail(db, task_id, message, retry=retry)
        if not retry and job_id:
            job = db.get(Job, job_id)
            if job:
                job.status = JobStatus.failed
                job.last_error = message
                db.commit()
        logger.warning("task failed", extra={"task": task_id, "kind": kind}, exc_info=exc)
    else:
        queue.complete(db, task_id)
        logger.info("task done", extra={"task": task_id, "kind": kind})
    return True


def schedule_nightly(db: Session, now: datetime | None = None) -> bool:
    """Queue the nightly tasks once per day, at or after the configured hour."""
    now = now or datetime.now(UTC)
    if now.hour < get_settings().nightly_hour_utc:
        return False
    claimed = db.execute(
        insert(ScheduledRun)
        .values(name="nightly", run_date=now.date())
        .on_conflict_do_nothing()
        .returning(ScheduledRun.name)
    ).first()
    if claimed:
        queue.enqueue(db, "expire")
        queue.enqueue(db, "reminders")
    db.commit()
    return claimed is not None
