"""Posting lifecycle: create, edit, publish, retry, expire, archive, restore."""

import csv
import io
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.core.storage import get_storage
from app.core.uploads import Upload
from app.db.audit import audit
from app.db.models import Job, JobFile, JobStatus, User
from app.ingest.duplicates import find_similar, hash_bytes, hash_fields, hash_text
from app.ingest.indexing import index_job
from app.ingest.queue import enqueue
from app.schemas.jobs import CsvResult, CsvRowResult, JobCreate, JobFields, JobPatch, PasteIn

EDITABLE = tuple(JobFields.model_fields)
MAX_CSV_ROWS = 500


def today() -> date:
    return datetime.now(UTC).date()


def get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("That posting does not exist. It may have been deleted.")
    return job


def _reject_exact_duplicate(db: Session, content_hash: str) -> None:
    existing = db.scalar(select(Job).where(Job.content_hash == content_hash))
    if existing:
        hint = (
            "Restore it instead of adding it again."
            if existing.status == JobStatus.archived
            else "Open it to make changes."
        )
        raise Conflict(
            f"This exact posting was already added as #{existing.id}. {hint}",
            code="duplicate_posting",
            details={"job_id": existing.id, "title": existing.title, "company": existing.company},
        )


def publish_problems(job: Job | JobFields) -> list[dict[str, str]]:
    problems = []
    for field, label in (
        ("company", "company"),
        ("title", "title"),
        ("description", "description"),
    ):
        if not getattr(job, field).strip():
            problems.append({"field": field, "message": f"Add a {label} before publishing."})
    if job.deadline and job.deadline < today():
        problems.append({"field": "deadline", "message": "The deadline has already passed."})
    return problems


def require_publishable(job: Job | JobFields) -> None:
    problems = publish_problems(job)
    if problems:
        raise AppError(
            "This posting is not ready to publish.", code="not_publishable", details=problems
        )


def create_from_form(
    db: Session, actor: User, body: JobCreate, source: str = "form", *, commit: bool = True
) -> Job:
    if body.action == "publish":
        require_publishable(body)
    content_hash = hash_fields(body)
    _reject_exact_duplicate(db, content_hash)
    job = Job(
        **body.model_dump(include=set(EDITABLE)),
        source=source,
        content_hash=content_hash,
        created_by=actor.id,
        status=JobStatus.draft,
    )
    similar = find_similar(db, body.company, body.title, body.deadline)
    job.duplicate_of_id = similar[0].id if similar else None
    db.add(job)
    db.flush()
    audit(db, actor.id, "created", "job", job.id, {"source": source})
    if body.action == "publish":
        _queue_for_index(db, actor, job)
    if commit:
        db.commit()
    return job


def create_from_text(db: Session, actor: User, body: PasteIn) -> Job:
    content_hash = hash_text(body.text)
    _reject_exact_duplicate(db, content_hash)
    job = Job(
        source="paste",
        raw_text=body.text,
        content_hash=content_hash,
        status=JobStatus.pending,
        auto_publish=body.auto_publish,
        created_by=actor.id,
    )
    db.add(job)
    db.flush()
    enqueue(db, "parse", job.id)
    audit(db, actor.id, "created", "job", job.id, {"source": "paste"})
    db.commit()
    return job


def create_from_file(db: Session, actor: User, upload: Upload, auto_publish: bool) -> Job:
    content_hash = hash_bytes(upload.data)
    _reject_exact_duplicate(db, content_hash)
    key = get_storage().save("jobs", upload.data, upload.extension)
    job = Job(
        source="upload",
        content_hash=content_hash,
        status=JobStatus.pending,
        auto_publish=auto_publish,
        created_by=actor.id,
    )
    db.add(job)
    db.flush()
    db.add(
        JobFile(
            job_id=job.id,
            path=key,
            original_name=upload.name,
            mime=upload.mime,
            sha256=content_hash,
        )
    )
    enqueue(db, "parse", job.id)
    audit(db, actor.id, "created", "job", job.id, {"source": "upload"})
    db.commit()
    return job


_TRUE = {"1", "true", "yes", "y"}


def _csv_row(raw: dict[str, str]) -> JobCreate:
    row = {k: v.strip() for k, v in raw.items() if k and isinstance(v, str) and v.strip()}
    data: dict[str, Any] = {k: v for k, v in row.items() if k in EDITABLE}
    data["skills"] = [s for s in row.get("skills", "").replace(";", ",").split(",") if s.strip()]
    data["remote"] = row.get("remote", "").lower() in _TRUE
    for field in ("stipend_min", "stipend_max"):
        if field in data:
            data[field] = data[field].replace(",", "")
    return JobCreate.model_validate(data)


def import_csv(db: Session, actor: User, data: bytes, publish: bool) -> CsvResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("Save the file as UTF-8 CSV and try again.", code="csv_encoding") from exc
    if "\x00" in text:
        raise AppError("That does not look like a CSV file.", code="file_type")
    reader = csv.DictReader(io.StringIO(text))
    header = {(h or "").strip() for h in reader.fieldnames or []}
    missing = {"company", "title", "description"} - header
    if missing:
        raise AppError(
            f"The header row is missing: {', '.join(sorted(missing))}.", code="csv_header"
        )
    rows: list[CsvRowResult] = []
    for number, raw in enumerate(reader, start=2):
        if len(rows) >= MAX_CSV_ROWS:
            raise AppError(f"Import at most {MAX_CSV_ROWS} rows at a time.", code="csv_rows")
        try:
            body = _csv_row({(k or "").strip(): v for k, v in raw.items()})
            body.action = "publish" if publish else "draft"
            with db.begin_nested():
                job = create_from_form(db, actor, body, source="csv", commit=False)
            note = "Likely duplicate, please review" if job.duplicate_of_id else "Added"
            rows.append(CsvRowResult(row=number, status="created", message=note, job_id=job.id))
        except Conflict as exc:
            rows.append(
                CsvRowResult(
                    row=number,
                    status="duplicate",
                    message=exc.message,
                    job_id=exc.details["job_id"],
                )
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            message = str(first["msg"]).removeprefix("Value error, ")
            rows.append(
                CsvRowResult(
                    row=number, status="invalid", message=f"{where}: {message}".lstrip(": ")
                )
            )
        except AppError as exc:
            detail = exc.details[0]["message"] if exc.details else exc.message
            rows.append(CsvRowResult(row=number, status="invalid", message=detail))
    db.commit()

    def count(status: str) -> int:
        return sum(1 for r in rows if r.status == status)

    return CsvResult(
        created=count("created"),
        duplicates=count("duplicate"),
        invalid=count("invalid"),
        rows=rows,
    )


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def update_job(db: Session, actor: User, job: Job, patch: JobPatch) -> Job:
    """Apply edits. A searchable job is re-indexed in the same transaction."""
    if job.status == JobStatus.pending:
        raise Conflict("This posting is still being processed. Try again in a moment.")
    current = {field: getattr(job, field) for field in EDITABLE}
    try:
        merged = JobFields.model_validate({**current, **patch.model_dump(exclude_unset=True)})
    except ValidationError as exc:
        message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
        raise AppError(message, code="invalid_input") from exc
    values = merged.model_dump()
    diff = {
        field: {"from": _plain(current[field]), "to": _plain(values[field])}
        for field in EDITABLE
        if current[field] != values[field]
    }
    if not diff:
        return job
    for field, value in values.items():
        setattr(job, field, value)
    if job.status == JobStatus.expired and (job.deadline is None or job.deadline >= today()):
        job.status = JobStatus.indexed
    if job.status == JobStatus.indexed:
        require_publishable(job)
        index_job(job)
    similar = find_similar(db, job.company, job.title, job.deadline, exclude_id=job.id)
    job.duplicate_of_id = similar[0].id if similar else None
    audit(db, actor.id, "edited", "job", job.id, diff)
    db.commit()
    return job


def _queue_for_index(db: Session, actor: User, job: Job) -> None:
    job.status = JobStatus.pending
    job.last_error = None
    job.parse_meta = {**job.parse_meta, "needs_review": False}
    enqueue(db, "index", job.id)
    audit(db, actor.id, "published", "job", job.id)


def publish(db: Session, actor: User, job: Job) -> Job:
    if job.status not in (JobStatus.draft, JobStatus.failed):
        raise Conflict("Only drafts and failed postings can be published.")
    require_publishable(job)
    _queue_for_index(db, actor, job)
    db.commit()
    return job


def retry(db: Session, actor: User, job: Job) -> Job:
    if job.status != JobStatus.failed:
        raise Conflict("Only failed postings can be retried.")
    job.status = JobStatus.pending
    job.last_error = None
    enqueue(db, "index" if job.company and job.title and job.description else "parse", job.id)
    audit(db, actor.id, "retried", "job", job.id)
    db.commit()
    return job


def reindex(db: Session, actor: User, job: Job) -> Job:
    if job.status != JobStatus.indexed:
        raise Conflict("Only published postings can be re-indexed.")
    job.status = JobStatus.pending
    enqueue(db, "index", job.id, {"alerts": False})
    audit(db, actor.id, "reindexed", "job", job.id)
    db.commit()
    return job


def set_aside(db: Session, actor: User, job: Job, status: JobStatus) -> Job:
    """Archive or expire. The row leaves search at once because search filters on status."""
    if job.status == status:
        return job
    if job.status == JobStatus.pending:
        raise Conflict("This posting is still being processed. Try again in a moment.")
    job.parse_meta = {**job.parse_meta, "previous_status": job.status}
    job.status = status
    audit(db, actor.id, status.value, "job", job.id)
    db.commit()
    return job


def restore(db: Session, actor: User, job: Job) -> Job:
    if job.status not in (JobStatus.archived, JobStatus.expired):
        raise Conflict("This posting is already active.")
    previous = job.parse_meta.get("previous_status") or JobStatus.draft
    if previous == JobStatus.indexed and job.deadline and job.deadline < today():
        previous = JobStatus.expired
        if job.status == JobStatus.expired:
            raise AppError(
                "The deadline has passed. Set a new deadline to reopen this posting.",
                code="deadline_passed",
            )
    if previous == JobStatus.indexed and job.embedding is None:
        previous = JobStatus.draft
    job.status = previous
    audit(db, actor.id, "restored", "job", job.id, {"status": previous})
    db.commit()
    return job


def delete_job(db: Session, actor: User, job: Job) -> None:
    if job.status not in (JobStatus.draft, JobStatus.failed, JobStatus.archived):
        raise Conflict("Archive this posting before deleting it.")
    paths = list(db.scalars(select(JobFile.path).where(JobFile.job_id == job.id)))
    audit(db, actor.id, "deleted", "job", job.id, {"title": job.title, "company": job.company})
    db.delete(job)
    db.commit()
    for path in paths:
        get_storage().delete(path)
