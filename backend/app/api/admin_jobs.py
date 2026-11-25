"""Coordinator routes for postings."""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from app.api.deps import Coordinator, Db
from app.core.errors import AppError, NotFound
from app.core.storage import get_storage
from app.core.uploads import read_document, read_limited
from app.db.models import AuditLog, Job, JobFile, JobStatus, User
from app.ingest import service
from app.ingest.duplicates import find_similar
from app.schemas.jobs import (
    AdminJobOut,
    AdminJobRow,
    AuditOut,
    BulkIn,
    CsvResult,
    DuplicateOut,
    JobCreate,
    JobPatch,
    Page,
    PasteIn,
)

router = APIRouter(prefix="/api/admin/jobs", tags=["admin"])

_SORTS: dict[str, Any] = {
    "updated": Job.updated_at.desc(),
    "deadline": Job.deadline.asc().nulls_last(),
    "company": func.lower(Job.company),
    "title": func.lower(Job.title),
    "status": Job.status,
}


def _row(job: Job) -> AdminJobRow:
    row = AdminJobRow.model_validate(job)
    row.needs_review = job.status == JobStatus.draft and bool(job.parse_meta.get("needs_review"))
    return row


def _detail(db: Db, job: Job) -> AdminJobOut:
    fields = {
        name: getattr(job, name)
        for name in AdminJobOut.model_fields
        if name not in ("indexed", "file_name", "duplicates")
    }
    out = AdminJobOut.model_validate(fields)
    out.indexed = job.embedding is not None and job.tsv is not None
    out.file_name = db.scalar(select(JobFile.original_name).where(JobFile.job_id == job.id))
    if job.status not in (JobStatus.archived, JobStatus.expired):
        out.duplicates = find_similar(db, job.company, job.title, job.deadline, job.id)
    return out


@router.get("", response_model=Page[AdminJobRow])
def list_jobs(
    _: Coordinator,
    db: Db,
    q: Annotated[str, Query(max_length=200)] = "",
    status: Annotated[list[JobStatus] | None, Query()] = None,
    company: Annotated[str, Query(max_length=160)] = "",
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    sort: Literal["updated", "deadline", "company", "title", "status"] = "updated",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[AdminJobRow]:
    conditions = []
    for word in q.split()[:8]:
        like = f"%{word.replace('%', '').replace('_', '')}%"
        conditions.append(
            or_(Job.title.ilike(like), Job.company.ilike(like), Job.location.ilike(like))
        )
    if status:
        conditions.append(Job.status.in_(status))
    if company:
        conditions.append(func.lower(Job.company) == company.lower())
    if deadline_from:
        conditions.append(Job.deadline >= deadline_from)
    if deadline_to:
        conditions.append(Job.deadline <= deadline_to)
    total = db.scalar(select(func.count()).select_from(Job).where(*conditions)) or 0
    jobs = db.scalars(
        select(Job)
        .where(*conditions)
        .order_by(_SORTS[sort], Job.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[_row(j) for j in jobs], total=total, page=page, page_size=page_size)


@router.get("/companies", response_model=list[str])
def companies(_: Coordinator, db: Db) -> list[str]:
    query = select(Job.company).where(Job.company != "").distinct().order_by(Job.company)
    return list(db.scalars(query))


@router.get("/similar", response_model=list[DuplicateOut])
def similar(
    _: Coordinator,
    db: Db,
    company: Annotated[str, Query(max_length=160)],
    title: Annotated[str, Query(max_length=200)],
    deadline: date | None = None,
) -> list[DuplicateOut]:
    return find_similar(db, company, title, deadline)


@router.post("", response_model=AdminJobOut, status_code=201)
def create(body: JobCreate, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.create_from_form(db, user, body))


@router.post("/paste", response_model=AdminJobOut, status_code=201)
def paste(body: PasteIn, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.create_from_text(db, user, body))


@router.post("/upload", response_model=AdminJobOut, status_code=201)
def upload(
    user: Coordinator,
    db: Db,
    file: Annotated[UploadFile, File()],
    auto_publish: Annotated[bool, Form()] = False,
) -> AdminJobOut:
    document = read_document(file)
    return _detail(db, service.create_from_file(db, user, document, auto_publish))


@router.post("/csv", response_model=CsvResult)
def import_csv(
    user: Coordinator,
    db: Db,
    file: Annotated[UploadFile, File()],
    publish: Annotated[bool, Form()] = False,
) -> CsvResult:
    return service.import_csv(db, user, read_limited(file), publish)


@router.post("/bulk")
def bulk(body: BulkIn, user: Coordinator, db: Db) -> dict[str, int]:
    done = skipped = 0
    for job_id in body.ids:
        try:
            job = service.get_job(db, job_id)
            if body.action == "retry":
                service.retry(db, user, job)
            elif body.action == "archive":
                service.set_aside(db, user, job, JobStatus.archived)
            else:
                service.set_aside(db, user, job, JobStatus.expired)
            done += 1
        except AppError:
            db.rollback()
            skipped += 1
    return {"done": done, "skipped": skipped}


@router.get("/{job_id}", response_model=AdminJobOut)
def detail(job_id: int, _: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.get_job(db, job_id))


@router.patch("/{job_id}", response_model=AdminJobOut)
def edit(job_id: int, body: JobPatch, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.update_job(db, user, service.get_job(db, job_id), body))


@router.delete("/{job_id}", status_code=204)
def delete(job_id: int, user: Coordinator, db: Db) -> None:
    service.delete_job(db, user, service.get_job(db, job_id))


@router.post("/{job_id}/publish", response_model=AdminJobOut)
def publish(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.publish(db, user, service.get_job(db, job_id)))


@router.post("/{job_id}/retry", response_model=AdminJobOut)
def retry(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.retry(db, user, service.get_job(db, job_id)))


@router.post("/{job_id}/reindex", response_model=AdminJobOut)
def reindex(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.reindex(db, user, service.get_job(db, job_id)))


@router.post("/{job_id}/archive", response_model=AdminJobOut)
def archive(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    job = service.get_job(db, job_id)
    return _detail(db, service.set_aside(db, user, job, JobStatus.archived))


@router.post("/{job_id}/expire", response_model=AdminJobOut)
def expire(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    job = service.get_job(db, job_id)
    return _detail(db, service.set_aside(db, user, job, JobStatus.expired))


@router.post("/{job_id}/restore", response_model=AdminJobOut)
def restore(job_id: int, user: Coordinator, db: Db) -> AdminJobOut:
    return _detail(db, service.restore(db, user, service.get_job(db, job_id)))


@router.get("/{job_id}/history", response_model=list[AuditOut])
def history(job_id: int, _: Coordinator, db: Db) -> list[AuditOut]:
    rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_id)
        .where(AuditLog.entity == "job", AuditLog.entity_id == str(job_id))
        .order_by(AuditLog.id.desc())
        .limit(100)
    )
    return [
        AuditOut(
            id=entry.id,
            action=entry.action,
            actor=name,
            diff=entry.diff,
            created_at=entry.created_at,
        )
        for entry, name in rows
    ]


@router.get("/{job_id}/file")
def download(job_id: int, _: Coordinator, db: Db) -> Response:
    file = db.scalar(select(JobFile).where(JobFile.job_id == job_id))
    if file is None:
        raise NotFound("No file was uploaded for this posting.")
    headers = {"Content-Disposition": f'attachment; filename="{file.original_name}"'}
    return Response(get_storage().read(file.path), media_type=file.mime, headers=headers)
