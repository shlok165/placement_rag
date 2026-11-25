"""Turns a posting into its searchable form: one embedding and one tsvector."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, literal_column

from app.db.models import Job, JobStatus
from app.embeddings import embed_passages


def job_passage(job: Job) -> str:
    place = "Remote" if job.remote and not job.location else job.location
    parts = [
        f"{job.title} at {job.company}.",
        f"{job.job_type.capitalize()} in {place}." if place else f"{job.job_type.capitalize()}.",
        f"Skills: {', '.join(job.skills)}." if job.skills else "",
        job.description,
        job.requirements,
    ]
    return " ".join(p for p in parts if p)


def set_tsv(job: Job) -> None:
    def weighted(text: str, weight: str) -> ColumnElement[Any]:
        return func.setweight(func.to_tsvector("english", text), literal_column(f"'{weight}'"))

    place = f"{job.location} {'remote' if job.remote else ''} {job.job_type}"
    job.tsv = (
        weighted(f"{job.title} {job.company}", "A")
        .op("||")(weighted(" ".join(job.skills), "B"))
        .op("||")(weighted(place, "B"))
        .op("||")(weighted(f"{job.description} {job.requirements}", "C"))
    )


def index_job(job: Job, *, vector: list[float] | None = None) -> None:
    """Set embedding, tsv and status together. The caller commits them in one transaction."""
    job.embedding = vector if vector is not None else embed_passages([job_passage(job)])[0]
    set_tsv(job)
    job.status = JobStatus.indexed
    job.last_error = None
    if job.published_at is None:
        job.published_at = datetime.now(UTC)
