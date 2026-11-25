"""Live-call budget and per-user chat quota, counted from the database."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ChatMessage, ChatSession, LlmCall, Role, User
from app.llm.types import BudgetExceeded

# Arbitrary key for the advisory lock that makes "count, then reserve" atomic.
_BUDGET_LOCK = 761_204


def day_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _live_count(db: Session, *conditions: Any) -> int:
    query = select(func.count()).select_from(LlmCall).where(LlmCall.is_live, *conditions)
    return db.scalar(query) or 0


def budget_status(db: Session, settings: Settings) -> dict[str, int]:
    today = _live_count(db, LlmCall.created_at >= day_start())
    total = _live_count(db)
    return {
        "live_today": today,
        "live_total": total,
        "daily_cap": settings.llm_daily_call_cap,
        "total_cap": settings.llm_total_call_cap,
        "remaining_today": max(
            0,
            min(settings.llm_daily_call_cap - today, settings.llm_total_call_cap - total),
        ),
    }


def reserve_live_call(
    db: Session,
    settings: Settings,
    *,
    user_id: int | None,
    purpose: str,
    scope: str,
    model: str,
    prompt_hash: str,
) -> int:
    """Record a live call before making it. Raises BudgetExceeded when a cap is reached."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _BUDGET_LOCK})
    if budget_status(db, settings)["remaining_today"] <= 0:
        db.rollback()
        raise BudgetExceeded("The live assistant budget for today is used up.")
    if scope.startswith("eval:"):
        used = _live_count(db, LlmCall.scope == scope)
        if used >= settings.llm_eval_call_cap:
            db.rollback()
            raise BudgetExceeded("The eval run reached its live call cap.")
    call = LlmCall(
        user_id=user_id,
        purpose=purpose,
        scope=scope,
        model=model,
        prompt_hash=prompt_hash,
        is_live=True,
        status="reserved",
    )
    db.add(call)
    db.commit()
    return call.id


def chat_quota(db: Session, user: User, settings: Settings) -> dict[str, int]:
    limit = (
        settings.coordinator_daily_turns
        if user.role == Role.coordinator
        else settings.student_daily_turns
    )
    used = (
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatSession.user_id == user.id,
                ChatMessage.role == "user",
                ChatMessage.created_at >= day_start(),
            )
        )
        or 0
    )
    return {"limit": limit, "used": used, "remaining": max(0, limit - used)}
