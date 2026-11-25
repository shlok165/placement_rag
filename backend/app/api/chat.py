"""Copilot conversations, confirmable actions and memory."""

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.agent import service
from app.agent.memory import active_facts
from app.agent.schemas import FactOut, MessageOut, PendingActionOut, SessionOut
from app.api.deps import CurrentUser, Db
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, TooManyRequests
from app.db.models import ChatMessage, ChatSession, MemoryFact, MessageFeedback, PendingAction, User
from app.llm.quota import chat_quota

router = APIRouter(prefix="/api", tags=["chat"])

POLL_S = 0.25


@router.get("/chat/status")
def status(user: CurrentUser, db: Db) -> dict[str, Any]:
    settings = get_settings()
    return {
        "mode": "live" if settings.is_live else "mock",
        "consent": user.consent_at is not None,
        "quota": chat_quota(db, user, settings),
    }


@router.get("/chat/sessions", response_model=list[SessionOut])
def sessions(user: CurrentUser, db: Db) -> Sequence[ChatSession]:
    query = select(ChatSession).where(ChatSession.user_id == user.id)
    return db.scalars(query.order_by(ChatSession.updated_at.desc()).limit(30)).all()


@router.post("/chat/sessions", response_model=SessionOut, status_code=201)
def create_session(user: CurrentUser, db: Db) -> ChatSession:
    session = ChatSession(user_id=user.id, title="New conversation", summary="")
    db.add(session)
    db.commit()
    return session


@router.delete("/chat/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, user: CurrentUser, db: Db) -> None:
    service.owned_session(db, user.id, session_id)
    db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    db.commit()


@router.get("/chat/sessions/{session_id}/messages", response_model=list[MessageOut])
def messages(session_id: int, user: CurrentUser, db: Db) -> list[MessageOut]:
    service.owned_session(db, user.id, session_id)
    return service.load_messages(db, user.id, session_id)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def _accept(db: Db, user: User, session_id: int, text: str) -> int:
    """Check consent and quota, then store the student's message."""
    if user.consent_at is None:
        raise Forbidden(
            "Agree to the AI data notice before using the copilot.", code="consent_required"
        )
    session = service.owned_session(db, user.id, session_id)
    quota = chat_quota(db, user, get_settings())
    if quota["remaining"] <= 0:
        raise TooManyRequests(
            f"You have used all {quota['limit']} copilot messages for today. They reset at "
            "midnight UTC. Search and browsing still work.",
            code="quota",
        )
    return service.start_message(db, session, text).id


@router.post("/chat/sessions/{session_id}/messages")
def send(
    session_id: int, body: MessageIn, request: Request, user: CurrentUser, db: Db
) -> StreamingResponse:
    message_id = _accept(db, user, session_id, body.text.strip() or body.text)
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()
    cancel = threading.Event()
    user_id = user.id

    def work() -> None:
        try:
            service.answer_message(user_id, session_id, message_id, events.put, cancel)
        finally:
            events.put(None)

    async def stream() -> AsyncIterator[str]:
        threading.Thread(target=work, daemon=True).start()
        try:
            while True:
                try:
                    event = await asyncio.to_thread(events.get, True, POLL_S)
                except queue.Empty:
                    if await request.is_disconnected():
                        return
                    continue
                if event is None:
                    return
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            # Reached on completion and when the browser closes the stream to stop the answer.
            cancel.set()

    headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)


# ------------------------------------------------------------------ actions and feedback


@router.post("/chat/actions/{action_id}/confirm", response_model=PendingActionOut)
def confirm(action_id: int, user: CurrentUser, db: Db) -> PendingAction:
    return service.confirm_action(db, user.id, action_id)


@router.post("/chat/actions/{action_id}/reject", response_model=PendingActionOut)
def reject(action_id: int, user: CurrentUser, db: Db) -> PendingAction:
    return service.reject_action(db, user.id, action_id)


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str = Field("", max_length=1000)


@router.post("/chat/messages/{message_id}/feedback", status_code=204)
def rate(message_id: int, body: FeedbackIn, user: CurrentUser, db: Db) -> None:
    owned = db.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatMessage.role == "assistant",
            ChatSession.user_id == user.id,
        )
    )
    if owned is None:
        raise NotFound("That message does not exist.")
    row = db.scalar(
        select(MessageFeedback).where(
            MessageFeedback.user_id == user.id, MessageFeedback.message_id == message_id
        )
    ) or MessageFeedback(user_id=user.id, message_id=message_id)
    row.rating = body.rating
    row.comment = body.comment or row.comment or ""
    db.add(row)
    db.commit()


# ------------------------------------------------------------------ memory


@router.get("/memory", response_model=list[FactOut])
def list_memory(user: CurrentUser, db: Db) -> list[MemoryFact]:
    return active_facts(db, user.id)


class FactIn(BaseModel):
    text: str = Field(min_length=3, max_length=300)


def _owned_fact(db: Db, user: User, fact_id: int) -> MemoryFact:
    fact = db.get(MemoryFact, fact_id)
    if fact is None or fact.user_id != user.id:
        raise NotFound("That memory does not exist.")
    return fact


@router.put("/memory/{fact_id}", response_model=FactOut)
def edit_memory(fact_id: int, body: FactIn, user: CurrentUser, db: Db) -> MemoryFact:
    fact = _owned_fact(db, user, fact_id)
    fact.text = " ".join(body.text.split())
    db.commit()
    return fact


@router.delete("/memory/{fact_id}", status_code=204)
def delete_memory(fact_id: int, user: CurrentUser, db: Db) -> None:
    db.delete(_owned_fact(db, user, fact_id))
    db.commit()
