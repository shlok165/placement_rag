"""Agent traces for coordinators: the steps behind one copilot answer.

Only two kinds of turn are visible: a coordinator's own, and a student's answer that the student
rated and chose to share. Opening a shared trace is written to the audit log.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.deps import Coordinator, Db
from app.core.errors import NotFound
from app.db.audit import audit
from app.db.models import ChatMessage, ChatSession, MessageFeedback

router = APIRouter(prefix="/api/admin/traces", tags=["admin"])
LIMIT = 100


class TraceRow(BaseModel):
    message_id: int
    created_at: datetime
    source: str
    rating: str | None
    question: str
    answer_kind: str | None
    tools: int
    latency_ms: int | None


def _visible(user_id: int) -> Any:
    shared = select(MessageFeedback.message_id).where(MessageFeedback.share_trace.is_(True))
    return (
        select(ChatMessage, ChatSession.user_id, MessageFeedback.rating, MessageFeedback.comment)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .outerjoin(MessageFeedback, MessageFeedback.message_id == ChatMessage.id)
        .where(
            ChatMessage.role == "assistant",
            or_(ChatSession.user_id == user_id, ChatMessage.id.in_(shared)),
        )
    )


def _question(db: Db, message: ChatMessage) -> str:
    asked = db.scalar(
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == message.session_id,
            ChatMessage.id < message.id,
            ChatMessage.role == "user",
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    return asked or ""


@router.get("", response_model=list[TraceRow])
def list_traces(user: Coordinator, db: Db) -> list[TraceRow]:
    rows = db.execute(_visible(user.id).order_by(ChatMessage.id.desc()).limit(LIMIT)).all()
    out = []
    for message, owner, rating, _ in rows:
        meta = message.meta or {}
        out.append(
            TraceRow(
                message_id=message.id,
                created_at=message.created_at,
                source="own" if owner == user.id else "shared",
                rating=rating,
                question=_question(db, message)[:160],
                answer_kind=meta.get("answer_kind"),
                tools=len(message.tool_calls or []),
                latency_ms=meta.get("latency_ms"),
            )
        )
    return out


@router.get("/{message_id}")
def get_trace(message_id: int, user: Coordinator, db: Db) -> dict[str, Any]:
    row = db.execute(_visible(user.id).where(ChatMessage.id == message_id)).first()
    if row is None:
        raise NotFound("That trace is not available.")
    message, owner, rating, comment = row
    if owner != user.id:
        audit(db, user.id, "trace_viewed", "chat_message", message.id)
        db.commit()
    meta = message.meta or {}
    return {
        "message_id": message.id,
        "created_at": message.created_at,
        "source": "own" if owner == user.id else "shared",
        "rating": rating,
        "comment": comment or "",
        "question": _question(db, message),
        "answer": message.content,
        "citations": message.citations or [],
        "tools": message.tool_calls or [],
        "checks": {
            "answer_kind": meta.get("answer_kind"),
            "structured": meta.get("structured"),
            "format_repairs": meta.get("format_repairs", 0),
            "fabrications_caught": meta.get("fabrications_caught", 0),
            "notice": meta.get("notice"),
            "draft": meta.get("draft") is not None,
        },
        "mode": meta.get("mode"),
        "iterations": meta.get("iterations"),
        "tokens": meta.get("tokens"),
        "latency_ms": meta.get("latency_ms"),
        "cache_hits": meta.get("cache_hits", 0),
    }
