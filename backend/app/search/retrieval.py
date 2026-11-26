"""Filters and the two retrievers: vector similarity and full-text search."""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, cast, func, literal, or_, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus


@dataclass
class Filters:
    job_type: str | None = None
    locations: list[str] = field(default_factory=list)
    remote: bool | None = None
    min_stipend: int | None = None
    closing_within_days: int | None = None
    exclude_ids: list[int] = field(default_factory=list)


def conditions(filters: Filters, today: date) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [
        Job.status == JobStatus.indexed,
        or_(Job.deadline.is_(None), Job.deadline >= today),
    ]
    if filters.job_type:
        clauses.append(Job.job_type == filters.job_type)
    if filters.locations:
        wanted = [loc.lower() for loc in filters.locations]
        clauses.append(func.lower(Job.location).in_(wanted))
    if filters.remote is not None:
        clauses.append(Job.remote.is_(filters.remote))
    if filters.min_stipend:
        clauses.append(func.coalesce(Job.stipend_max, Job.stipend_min, 0) >= filters.min_stipend)
    if filters.closing_within_days is not None:
        clauses.append(Job.deadline <= today + timedelta(days=filters.closing_within_days))
    if filters.exclude_ids:
        clauses.append(Job.id.not_in(filters.exclude_ids))
    return clauses


def semantic(
    db: Session,
    vector: list[float],
    clauses: list[ColumnElement[bool]],
    limit: int,
    min_similarity: float = 0.0,
) -> list[tuple[int, float]]:
    """Nearest postings as (job id, cosine similarity), best first."""
    # Filters are applied while walking the index, so ask it to keep going until `limit` is met.
    db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    distance = Job.embedding.cosine_distance(vector)
    # Order by distance alone: a second sort key stops Postgres from using the HNSW index, which
    # turned every query into a full scan (see docs/PERFORMANCE.md). Ties are ordered below.
    rows = db.execute(
        select(Job.id, (1 - distance).label("similarity"))
        .where(*clauses, Job.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    ).all()
    hits = sorted(((row.id, float(row.similarity)) for row in rows), key=lambda h: (-h[1], h[0]))
    return [hit for hit in hits if hit[1] >= min_similarity]


MAX_TERMS = 16


def query_terms(db: Session, query: str) -> list[str]:
    """Stemmed query words without stop words."""
    lexemes = func.tsvector_to_array(func.to_tsvector("english", query))
    return list(db.scalar(select(lexemes)) or [])[:MAX_TERMS]


def _as_tsquery(lexeme: str) -> Any:
    escaped = lexeme.replace("\\", "\\\\").replace("'", "''")
    return cast(f"'{escaped}'", TSQUERY)


def keyword(
    db: Session, query: str, clauses: list[ColumnElement[bool]], limit: int
) -> list[tuple[int, float]]:
    """Full-text matches as (job id, score), best first.

    Any term may match. Postgres ranking has no inverse document frequency, so each term is
    weighted by how rare it is. Otherwise words like "intern" would drown out the topic.
    """
    terms = query_terms(db, query)
    if not terms:
        return []
    queries = [_as_tsquery(term) for term in terms]
    live = Job.status == JobStatus.indexed
    counts = db.execute(
        select(func.count(), *(func.count().filter(Job.tsv.op("@@")(q)) for q in queries)).where(
            live
        )
    ).one()
    total = counts[0]
    score: ColumnElement[Any] = literal(0.0)
    for tsquery, found in zip(queries, counts[1:], strict=True):
        rarity = math.log(1 + (total - found + 0.5) / (found + 0.5))
        # Normalisation 1 damps long documents.
        score = score + rarity * func.ts_rank(Job.tsv, tsquery, 1)
    rows = db.execute(
        select(Job.id, score.label("score"))
        .where(*clauses, or_(*(Job.tsv.op("@@")(q) for q in queries)))
        .order_by(score.desc(), Job.id)
        .limit(limit)
    )
    return [(row.id, float(row.score)) for row in rows]
