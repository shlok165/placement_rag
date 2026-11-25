"""Coordinator eval workspace: sets, cases, runs and promoted student feedback."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import Coordinator, Db
from app.core.errors import AppError, Conflict, NotFound
from app.db.audit import audit
from app.db.models import ChatMessage, EvalCase, EvalRun, EvalSet, Job, MessageFeedback
from app.ingest.queue import enqueue
from app.schemas.jobs import Page

router = APIRouter(prefix="/api/admin/evals", tags=["admin"])

FEEDBACK_SET = "Student feedback"


class SetIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    description: str = Field("", max_length=500)


class CaseIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    relevant_job_ids: list[int] = Field(default_factory=list, max_length=100)
    notes: str = Field("", max_length=500)


class CaseOut(CaseIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int
    profile_snapshot: dict[str, Any]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    set_id: int | None
    kind: str
    status: str
    metrics: dict[str, Any]
    created_at: datetime


def _set(db: Db, set_id: int) -> EvalSet:
    row = db.get(EvalSet, set_id)
    if row is None:
        raise NotFound("That eval set does not exist.")
    return row


def _case(db: Db, case_id: int) -> EvalCase:
    row = db.get(EvalCase, case_id)
    if row is None:
        raise NotFound("That case does not exist.")
    return row


def _check_jobs(db: Db, ids: list[int]) -> None:
    known = set(db.scalars(select(Job.id).where(Job.id.in_(ids))))
    unknown = sorted(set(ids) - known)
    if unknown:
        listed = ", ".join(f"#{i}" for i in unknown)
        raise AppError(
            f"These postings do not exist: {listed}.",
            code="unknown_jobs",
            details=[{"field": "relevant_job_ids", "message": f"Unknown: {listed}"}],
        )


@router.get("/sets")
def list_sets(_: Coordinator, db: Db) -> list[dict[str, Any]]:
    rows = db.execute(
        select(EvalSet, func.count(EvalCase.id))
        .outerjoin(EvalCase, EvalCase.set_id == EvalSet.id)
        .group_by(EvalSet.id)
        .order_by(EvalSet.id)
    )
    return [{"id": s.id, "name": s.name, "description": s.description, "cases": n} for s, n in rows]


@router.post("/sets", status_code=201)
def create_set(body: SetIn, user: Coordinator, db: Db) -> dict[str, int]:
    if db.scalar(select(EvalSet.id).where(EvalSet.name == body.name)):
        raise Conflict("A set with this name already exists.")
    row = EvalSet(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user.id, "eval_set_created", "eval_set", row.id)
    db.commit()
    return {"id": row.id}


@router.get("/sets/{set_id}/cases", response_model=Page[CaseOut])
def list_cases(
    set_id: int,
    _: Coordinator,
    db: Db,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[CaseOut]:
    _set(db, set_id)
    total = db.scalar(select(func.count()).select_from(EvalCase).where(EvalCase.set_id == set_id))
    rows = db.scalars(
        select(EvalCase)
        .where(EvalCase.set_id == set_id)
        .order_by(EvalCase.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [CaseOut.model_validate(r) for r in rows]
    return Page(items=items, total=total or 0, page=page, page_size=page_size)


@router.post("/sets/{set_id}/cases", response_model=CaseOut, status_code=201)
def create_case(set_id: int, body: CaseIn, user: Coordinator, db: Db) -> EvalCase:
    _set(db, set_id)
    _check_jobs(db, body.relevant_job_ids)
    row = EvalCase(set_id=set_id, profile_snapshot={}, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user.id, "eval_case_created", "eval_case", row.id)
    db.commit()
    return row


@router.put("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: int, body: CaseIn, user: Coordinator, db: Db) -> EvalCase:
    row = _case(db, case_id)
    _check_jobs(db, body.relevant_job_ids)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    audit(db, user.id, "eval_case_edited", "eval_case", case_id)
    db.commit()
    return row


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: int, user: Coordinator, db: Db) -> None:
    db.delete(_case(db, case_id))
    audit(db, user.id, "eval_case_deleted", "eval_case", case_id)
    db.commit()


@router.get("/runs", response_model=list[RunOut])
def list_runs(_: Coordinator, db: Db) -> list[EvalRun]:
    return list(db.scalars(select(EvalRun).order_by(EvalRun.id.desc()).limit(15)))


@router.post("/sets/{set_id}/run", response_model=RunOut, status_code=202)
def start_run(set_id: int, user: Coordinator, db: Db) -> EvalRun:
    """Queue a retrieval eval. No LLM calls."""
    _set(db, set_id)
    busy = select(EvalRun.id).where(EvalRun.set_id == set_id, EvalRun.status == "queued")
    if db.scalar(busy):
        raise Conflict("A run for this set is already in progress.")
    run = EvalRun(set_id=set_id, kind="retrieval", status="queued", config={"corpus": "live"})
    db.add(run)
    db.flush()
    enqueue(db, "eval", payload={"run_id": run.id})
    audit(db, user.id, "eval_run_started", "eval_run", run.id)
    db.commit()
    return run


# ------------------------------------------------------------------ student feedback


def _question_before(db: Db, message: ChatMessage) -> str:
    return (
        db.scalar(
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == message.session_id,
                ChatMessage.role == "user",
                ChatMessage.id < message.id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
        or ""
    )


@router.get("/feedback")
def list_feedback(_: Coordinator, db: Db) -> list[dict[str, Any]]:
    """Rated answers, without names."""
    rows = db.execute(
        select(MessageFeedback, ChatMessage)
        .join(ChatMessage, ChatMessage.id == MessageFeedback.message_id)
        .order_by(MessageFeedback.id.desc())
        .limit(50)
    )
    return [
        {
            "id": f.id,
            "rating": f.rating,
            "comment": f.comment,
            "question": _question_before(db, m),
            "answer": m.content[:600],
            "cited_job_ids": [c["job_id"] for c in m.citations],
            "promoted": f.promoted_case_id is not None,
            "created_at": f.created_at,
        }
        for f, m in rows
    ]


@router.post("/feedback/{feedback_id}/promote", response_model=CaseOut, status_code=201)
def promote(feedback_id: int, user: Coordinator, db: Db) -> EvalCase:
    """Turn a rated answer into an eval case. Postings cited in a good answer become labels."""
    row = db.get(MessageFeedback, feedback_id)
    if row is None:
        raise NotFound("That feedback no longer exists.")
    if row.promoted_case_id is not None:
        raise Conflict("This feedback is already an eval case.")
    message = db.get(ChatMessage, row.message_id)
    assert message is not None
    target = db.scalar(select(EvalSet).where(EvalSet.name == FEEDBACK_SET))
    if target is None:
        target = EvalSet(name=FEEDBACK_SET, description="Cases taken from rated copilot answers.")
        db.add(target)
        db.flush()
    cited = [c["job_id"] for c in message.citations] if row.rating == "up" else []
    case = EvalCase(
        set_id=target.id,
        query=_question_before(db, message)[:300],
        # The student's profile is left out on purpose: coordinators do not need it.
        profile_snapshot={},
        relevant_job_ids=cited,
        notes=f"Rated {row.rating}. {row.comment}"[:500],
    )
    db.add(case)
    db.flush()
    row.promoted_case_id = case.id
    audit(db, user.id, "feedback_promoted", "eval_case", case.id)
    db.commit()
    return case
