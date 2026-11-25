"""Runs one chat turn end to end: history, agent, memory proposals and storage."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.loop import run_turn, turn_messages
from app.agent.memory import active_facts, propose_facts, summarise
from app.agent.prompts import system_prompt
from app.agent.schemas import MessageOut, PendingActionOut
from app.agent.tools import ToolContext
from app.api.student import save, track, visible_job
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound
from app.db.models import (
    ApplicationStatus,
    ChatMessage,
    ChatSession,
    MemoryFact,
    MessageFeedback,
    PendingAction,
    StudentProfile,
)
from app.db.session import get_sessionmaker
from app.llm.client import get_llm
from app.schemas.student import PreferencesIn
from app.search.profiles import refresh_embedding

logger = logging.getLogger("app.agent")

Emit = Callable[[dict[str, Any]], None]
CHUNK_WORDS = 4
CHUNK_PAUSE_S = 0.025


def owned_session(db: Session, user_id: int, session_id: int) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise NotFound("That conversation does not exist.")
    return session


def message_out(
    message: ChatMessage, actions: list[PendingAction], feedback: str | None = None
) -> MessageOut:
    meta = message.meta or {}
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=message.citations or [],
        suggested_followups=meta.get("followups", []),
        pending_actions=[PendingActionOut.model_validate(a) for a in actions],
        notice=meta.get("notice"),
        stopped=meta.get("stopped", False),
        feedback=feedback,
        created_at=message.created_at,
    )


def load_messages(db: Session, user_id: int, session_id: int) -> list[MessageOut]:
    messages = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    ).all()
    ids = [m.id for m in messages]
    actions: dict[int, list[PendingAction]] = {}
    for action in db.scalars(
        select(PendingAction).where(PendingAction.message_id.in_(ids)).order_by(PendingAction.id)
    ):
        actions.setdefault(action.message_id or 0, []).append(action)
    ratings = dict(
        db.execute(
            select(MessageFeedback.message_id, MessageFeedback.rating).where(
                MessageFeedback.user_id == user_id, MessageFeedback.message_id.in_(ids)
            )
        )
        .tuples()
        .all()
    )
    return [message_out(m, actions.get(m.id, []), ratings.get(m.id)) for m in messages]


def _history(db: Session, session: ChatSession, before_id: int) -> list[dict[str, Any]]:
    """Recent messages as they are; older ones folded into the session summary."""
    keep = get_settings().agent_history_messages
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id, ChatMessage.id < before_id)
        .order_by(ChatMessage.id)
    ).all()
    older, recent = messages[:-keep], messages[-keep:]
    if older:
        session.summary = summarise(list(older))
    return [{"role": m.role, "content": m.content[:1500]} for m in recent if m.content]


def start_message(db: Session, session: ChatSession, text: str) -> ChatMessage:
    if session.title == "New conversation":
        session.title = text.strip().replace("\n", " ")[:60]
    session.updated_at = datetime.now(UTC)
    message = ChatMessage(
        session_id=session.id, role="user", content=text, tool_calls=[], citations=[], meta={}
    )
    db.add(message)
    db.commit()
    return message


def _stream(text: str, emit: Emit, cancelled: Callable[[], bool], pause: float) -> str:
    """Send the checked answer in small pieces. Returns what was sent."""
    words = text.split(" ")
    sent = ""
    for start in range(0, len(words), CHUNK_WORDS):
        if cancelled():
            return sent
        piece = " ".join(words[start : start + CHUNK_WORDS])
        if start + CHUNK_WORDS < len(words):
            piece += " "
        emit({"type": "delta", "text": piece})
        sent += piece
        if pause:
            time.sleep(pause)
    return sent


def answer_message(
    user_id: int,
    session_id: int,
    message_id: int,
    emit: Emit,
    cancel: threading.Event,
    *,
    pause: float = CHUNK_PAUSE_S,
) -> None:
    """Worker for one turn. Uses its own database session and never raises."""
    try:
        with get_sessionmaker()() as db:
            _answer(db, user_id, session_id, message_id, emit, cancel, pause)
    except Exception as exc:
        logger.error("chat turn failed", exc_info=exc)
        emit(
            {
                "type": "error",
                "message": "The copilot ran into a problem. Your message is kept. Please retry.",
            }
        )


def _answer(
    db: Session,
    user_id: int,
    session_id: int,
    message_id: int,
    emit: Emit,
    cancel: threading.Event,
    pause: float,
) -> None:
    settings = get_settings()
    session = owned_session(db, user_id, session_id)
    message = db.get(ChatMessage, message_id)
    assert message is not None
    llm = get_llm()
    ctx = ToolContext(db, user_id)
    facts = [f.text for f in active_facts(db, user_id)]
    history = _history(db, session, message.id)
    messages = turn_messages(
        system_prompt(ctx.today, facts, session.summary), history, message.content
    )
    emit({"type": "status", "text": "Thinking"})
    result = run_turn(
        llm,
        ctx,
        messages,
        settings,
        emit=lambda text: emit({"type": "status", "text": text}),
        cancelled=cancel.is_set,
    )
    sent = "" if result.stopped else _stream(result.answer, emit, cancel.is_set, pause)
    stopped = result.stopped or len(sent) < len(result.answer)

    reply = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=sent,
        tool_calls=[t.model_dump() for t in ctx.trace],
        citations=[] if result.stopped else [c.model_dump() for c in result.citations],
        meta={
            "followups": [] if stopped else result.followups,
            "notice": result.notice,
            "stopped": stopped,
            "mode": result.mode,
            "structured": result.structured,
            "iterations": result.iterations,
            "tokens": result.tokens,
        },
    )
    db.add(reply)
    db.flush()
    proposals = [] if stopped else list(ctx.proposals)
    if not stopped:
        for fact in propose_facts(llm, db, user_id, message.content):
            proposals.append(
                {
                    "kind": "remember",
                    "label": f"Remember: {fact.text}",
                    "payload": {"kind": fact.kind, "text": fact.text, "source": message.id},
                }
            )
    actions = [PendingAction(user_id=user_id, message_id=reply.id, **p) for p in proposals]
    db.add_all(actions)
    session.updated_at = datetime.now(UTC)
    db.commit()
    emit({"type": "done", "message": message_out(reply, actions).model_dump(mode="json")})


# ---------------------------------------------------------------- confirmable actions


def _owned_action(db: Session, user_id: int, action_id: int) -> PendingAction:
    action = db.scalar(
        select(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.user_id == user_id)
        .with_for_update()
    )
    if action is None:
        raise NotFound("That action does not exist.")
    if action.status != "pending":
        raise Conflict("You already answered this one.")
    return action


def confirm_action(db: Session, user_id: int, action_id: int) -> PendingAction:
    action = _owned_action(db, user_id, action_id)
    payload = action.payload
    if action.kind == "save_job":
        visible_job(db, payload["job_id"])
        save(db, user_id, payload["job_id"])
    elif action.kind == "track_application":
        visible_job(db, payload["job_id"])
        status = ApplicationStatus(payload["status"])
        track(db, user_id, payload["job_id"], status, payload.get("notes") or None)
    elif action.kind == "update_preferences":
        profile = db.get(StudentProfile, user_id) or StudentProfile(user_id=user_id)
        merged = PreferencesIn.model_validate({**(profile.preferences or {}), **payload})
        profile.preferences = merged.model_dump()
        db.add(profile)
        refresh_embedding(profile)
    elif action.kind == "remember":
        db.add(
            MemoryFact(
                user_id=user_id,
                kind=payload["kind"],
                text=payload["text"],
                source_message_id=payload.get("source"),
            )
        )
    action.status = "confirmed"
    action.resolved_at = datetime.now(UTC)
    db.commit()
    return action


def reject_action(db: Session, user_id: int, action_id: int) -> PendingAction:
    action = _owned_action(db, user_id, action_id)
    action.status = "rejected"
    action.resolved_at = datetime.now(UTC)
    db.commit()
    return action
