"""Exact and near-duplicate detection for postings."""

import hashlib
import re
from datetime import date, timedelta

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus
from app.schemas.jobs import DuplicateOut, JobFields

COMPANY_MIN = 88.0
TITLE_MIN = 85.0
DEADLINE_WINDOW = timedelta(days=3)

_SUFFIXES = re.compile(r"\b(pvt|private|ltd|limited|inc|llp|llc|technologies|india)\b\.?", re.I)


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def hash_text(text: str) -> str:
    return hashlib.sha256(normalise(text).encode()).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_fields(fields: JobFields) -> str:
    parts = [
        fields.company,
        fields.title,
        fields.location,
        fields.job_type,
        str(fields.deadline),
        fields.description,
    ]
    return hash_text(" | ".join(parts))


def _company(name: str) -> str:
    return normalise(_SUFFIXES.sub("", name))


def _close(first: date | None, second: date | None) -> bool:
    if first is None or second is None:
        return first == second
    return abs(first - second) <= DEADLINE_WINDOW


def find_similar(
    db: Session, company: str, title: str, deadline: date | None, exclude_id: int | None = None
) -> list[DuplicateOut]:
    """Live postings whose company, title and deadline are near-identical."""
    if not company or not title:
        return []
    query = select(Job).where(Job.status != JobStatus.archived)
    if exclude_id is not None:
        query = query.where(Job.id != exclude_id)
    if deadline is not None:
        low, high = deadline - DEADLINE_WINDOW, deadline + DEADLINE_WINDOW
        query = query.where(Job.deadline.between(low, high))
    else:
        query = query.where(or_(Job.deadline.is_(None)))
    matches = []
    for job in db.scalars(query):
        company_score = fuzz.ratio(_company(company), _company(job.company))
        title_score = fuzz.token_sort_ratio(normalise(title), normalise(job.title))
        if (
            company_score >= COMPANY_MIN
            and title_score >= TITLE_MIN
            and _close(deadline, job.deadline)
        ):
            matches.append(
                DuplicateOut(
                    id=job.id,
                    company=job.company,
                    title=job.title,
                    deadline=job.deadline,
                    status=job.status,
                    similarity=round(min(company_score, title_score) / 100, 2),
                )
            )
    return sorted(matches, key=lambda m: m.similarity, reverse=True)[:5]
