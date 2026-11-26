"""Load the synthetic corpus into a database."""

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvalCase, EvalSet, Job, JobStatus
from app.embeddings import embed_passages
from app.ingest.duplicates import hash_text
from app.ingest.indexing import index_job, job_passage
from evals.cases import PROFILES, Case, build_cases
from evals.dataset import MAIN, SyntheticJob, Variant, generate_jobs
from evals.harness import LabelledCase

SET_NAME = "Synthetic retrieval set"


def _hash(key: str) -> str:
    return hash_text(f"synthetic posting {key}")


def load_jobs(
    db: Session,
    reference: date,
    created_by: int | None = None,
    limit: int | None = None,
    *,
    variant: Variant = MAIN,
    transform: Callable[[SyntheticJob], SyntheticJob] | None = None,
) -> dict[str, int]:
    """Insert missing synthetic jobs. Returns dataset key -> job id."""
    rows: list[SyntheticJob] = generate_jobs(reference, variant)[:limit]
    if transform:
        rows = [transform(r) for r in rows]
    by_hash = {_hash(r.key): r for r in rows}
    existing = {
        content_hash: job_id
        for job_id, content_hash in db.execute(
            select(Job.id, Job.content_hash).where(Job.content_hash.in_(by_hash))
        )
    }
    fresh: list[Job] = []
    for content_hash, row in by_hash.items():
        if content_hash not in existing:
            fresh.append(
                Job(
                    **row.fields,
                    source="seed",
                    content_hash=content_hash,
                    created_by=created_by,
                    status=JobStatus.draft,
                )
            )
    vectors = embed_passages([job_passage(j) for j in fresh])
    for job, vector in zip(fresh, vectors, strict=True):
        index_job(job, vector=vector)
    db.add_all(fresh)
    db.commit()
    ids = {**existing, **{j.content_hash: j.id for j in fresh}}
    return {row.key: ids[h] for h, row in by_hash.items()}


def labelled_cases(
    ids: dict[str, int],
    reference: date,
    variant: Variant = MAIN,
    builder: Callable[[list[SyntheticJob]], list[Case]] = build_cases,
) -> list[LabelledCase]:
    """Labels always come from the clean generator output, never from transformed text."""
    jobs = [j for j in generate_jobs(reference, variant) if j.key in ids]
    return [
        LabelledCase(c.query, PROFILES[c.profile], {ids[k] for k in c.relevant}, c.slice)
        for c in builder(jobs)
    ]


def load_eval_set(db: Session, ids: dict[str, int], reference: date) -> None:
    """Store the labelled cases, so coordinators can see, edit and run them."""
    if db.scalar(select(EvalSet.id).where(EvalSet.name == SET_NAME)):
        return
    eval_set = EvalSet(
        name=SET_NAME,
        description="Query and profile pairs with known answers, built from synthetic postings.",
        created_at=datetime.combine(reference, time()),
    )
    db.add(eval_set)
    db.flush()
    for case in labelled_cases(ids, reference):
        snapshot: dict[str, Any] = {**case.profile, "slice": case.slice}
        db.add(
            EvalCase(
                set_id=eval_set.id,
                query=case.query,
                profile_snapshot=snapshot,
                relevant_job_ids=sorted(case.relevant),
                notes=case.slice,
            )
        )
    db.commit()
