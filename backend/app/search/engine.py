"""Search entry point. No dependency on the agent or on web code."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Job
from app.embeddings import embed_query
from app.search.config import SearchConfig, get_search_config
from app.search.cross import reorder
from app.search.fusion import fuse
from app.search.ranking import Profile, score_job
from app.search.retrieval import Filters, conditions, keyword, semantic

Sort = Literal["relevance", "deadline", "newest", "stipend"]
Mode = Literal["hybrid", "semantic", "keyword"]


@dataclass
class Hit:
    job: Job
    score: float
    breakdown: dict[str, Any] | None = None


@dataclass
class Results:
    hits: list[Hit]
    total: int
    candidate_ids: list[int]
    top_similarity: float | None = None


_SORTS: dict[str, Any] = {
    "deadline": (Job.deadline.asc().nulls_last(), Job.id),
    "newest": (Job.published_at.desc().nulls_last(), Job.id.desc()),
    "stipend": (func.coalesce(Job.stipend_max, Job.stipend_min, 0).desc(), Job.id),
}


def _load(db: Session, ids: list[int]) -> dict[int, Job]:
    return {job.id: job for job in db.scalars(select(Job).where(Job.id.in_(ids)))} if ids else {}


def _candidates(
    db: Session, query: str, clauses: list[Any], config: SearchConfig, mode: Mode
) -> tuple[list[tuple[int, float]], float | None]:
    vector_hits: list[tuple[int, float]] = []
    text_hits: list[tuple[int, float]] = []
    if mode != "keyword":
        vector_hits = semantic(
            db, embed_query(query), clauses, config.candidates, config.min_similarity
        )
    if mode != "semantic":
        text_hits = keyword(db, query, clauses, config.candidates)
    top = vector_hits[0][1] if vector_hits else None
    if mode == "semantic":
        return vector_hits, top
    if mode == "keyword":
        return text_hits, top
    return fuse(vector_hits, text_hits, config.fusion), top


def _browse(
    db: Session, clauses: list[Any], sort: Sort, limit: int, offset: int
) -> tuple[list[Job], int]:
    total = db.scalar(select(func.count()).select_from(Job).where(*clauses)) or 0
    order = _SORTS.get(sort, _SORTS["deadline"])
    jobs = db.scalars(select(Job).where(*clauses).order_by(*order).offset(offset).limit(limit))
    return list(jobs), total


def search(
    db: Session,
    query: str,
    filters: Filters | None = None,
    *,
    profile: Profile | None = None,
    sort: Sort = "relevance",
    limit: int = 20,
    offset: int = 0,
    mode: Mode = "hybrid",
    config: SearchConfig | None = None,
    today: date | None = None,
) -> Results:
    config = config or get_search_config()
    today = today or datetime.now(UTC).date()
    clauses = conditions(filters or Filters(), today)
    query = " ".join(query.split())
    personal = profile is not None and not profile.is_empty
    top_similarity: float | None = None

    if query:
        ranked, top_similarity = _candidates(db, query, clauses, config, mode)
        pool = _load(db, [job_id for job_id, _ in ranked])
        if config.cross_encoder.enabled:
            ranked = reorder(query, ranked, pool, config.cross_encoder)
        scores = dict(ranked)
        best, worst = max(scores.values(), default=0.0), min(scores.values(), default=0.0)
        hits = []
        for job_id, score in ranked:
            job = pool[job_id]
            if personal and profile is not None:
                # Fused scores bunch together, so stretch them over 0..1 before mixing.
                relevance = (score - worst) / (best - worst) if best > worst else 1.0
                detail = score_job(job, profile, config.rerank, today, relevance)
                hits.append(Hit(job, detail["score"], detail))
            else:
                hits.append(Hit(job, score))
    elif personal and profile is not None and sort == "relevance":
        # No query: rank every open posting for this student.
        jobs, _ = _browse(db, clauses, "deadline", 1000, 0)
        hits = []
        for job in jobs:
            detail = score_job(job, profile, config.rerank, today)
            hits.append(Hit(job, detail["score"], detail))
        ranked = [(h.job.id, h.score) for h in hits]
    else:
        jobs, total = _browse(db, clauses, sort, limit, offset)
        hits = []
        for job in jobs:
            if personal and profile is not None:
                detail = score_job(job, profile, config.rerank, today)
                hits.append(Hit(job, detail["score"], detail))
            else:
                hits.append(Hit(job, 0.0))
        return Results(hits, total, [j.id for j in jobs])

    if sort == "relevance":
        if personal:
            hits.sort(key=lambda h: (-h.score, h.job.id))
    elif sort == "deadline":
        hits.sort(key=lambda h: (h.job.deadline or date.max, h.job.id))
    elif sort == "newest":
        hits.sort(key=lambda h: -(h.job.published_at or h.job.created_at).timestamp())
    else:
        hits.sort(key=lambda h: -(h.job.stipend_max or h.job.stipend_min or 0))
    return Results(
        hits[offset : offset + limit], len(hits), [job_id for job_id, _ in ranked], top_similarity
    )


def similar_jobs(db: Session, job: Job, limit: int = 4, today: date | None = None) -> list[Job]:
    if job.embedding is None:
        return []
    today = today or datetime.now(UTC).date()
    clauses = conditions(Filters(exclude_ids=[job.id]), today)
    ids = [job_id for job_id, _ in semantic(db, list(job.embedding), clauses, limit)]
    pool = _load(db, ids)
    return [pool[i] for i in ids]
