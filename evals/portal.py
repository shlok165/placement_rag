"""Retrieval evals started from the coordinator portal, on the live corpus."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvalCase, EvalRun, Job, JobStatus
from evals.harness import STANDARD_CONFIGS, LabelledCase, evaluate


def run_retrieval_eval(db: Session, run_id: int) -> None:
    run = db.get(EvalRun, run_id)
    if run is None:
        return
    open_ids = set(db.scalars(select(Job.id).where(Job.status == JobStatus.indexed)))
    cases = []
    skipped = 0
    for case in db.scalars(select(EvalCase).where(EvalCase.set_id == run.set_id)):
        # A label that points at a closed posting cannot be found, so it would only add noise.
        relevant = open_ids.intersection(case.relevant_job_ids)
        if not relevant:
            skipped += 1
            continue
        slice_name = str(case.profile_snapshot.get("slice") or "all")
        profile = {k: v for k, v in case.profile_snapshot.items() if k != "slice"}
        cases.append(LabelledCase(case.query, profile, relevant, slice_name))
    if not cases:
        run.status = "failed"
        run.metrics = {"message": "No case has an open relevant posting.", "skipped": skipped}
    else:
        results = [evaluate(db, cases, config) for config in STANDARD_CONFIGS]
        run.status = "done"
        run.metrics = {"configs": results, "skipped": skipped}
    db.commit()
