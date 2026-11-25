"""Coordinator accounts: list, invite, deactivate."""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.api.deps import Coordinator, Db
from app.core.errors import AppError, Conflict, NotFound
from app.core.security import hash_token
from app.db.audit import audit
from app.db.models import Invite, Role, User, UserSession
from app.schemas.auth import InviteCreated, InviteIn, InviteOut, UserOut

router = APIRouter(prefix="/api/admin/team", tags=["admin"])


@router.get("", response_model=list[UserOut])
def list_team(_: Coordinator, db: Db) -> Sequence[User]:
    query = select(User).where(User.role == Role.coordinator, User.is_active).order_by(User.id)
    return db.scalars(query).all()


@router.get("/invites", response_model=list[InviteOut])
def list_invites(_: Coordinator, db: Db) -> Sequence[Invite]:
    query = select(Invite).where(Invite.accepted_at.is_(None)).order_by(Invite.id.desc())
    return db.scalars(query).all()


@router.post("/invites", response_model=InviteCreated, status_code=201)
def create_invite(body: InviteIn, user: Coordinator, db: Db) -> InviteCreated:
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise Conflict("Someone with this email already has an account.", code="email_taken")
    token = secrets.token_urlsafe(32)
    db.execute(delete(Invite).where(Invite.email == body.email, Invite.accepted_at.is_(None)))
    invite = Invite(
        email=body.email,
        token_hash=hash_token(token),
        invited_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invite)
    db.flush()
    audit(db, user.id, "invite_created", "invite", invite.id)
    db.commit()
    base = InviteOut.model_validate(invite).model_dump()
    return InviteCreated(**base, link=f"/accept-invite#{token}")


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, user: Coordinator, db: Db) -> None:
    invite = db.get(Invite, invite_id)
    if invite is None or invite.accepted_at:
        raise NotFound("That invite no longer exists.")
    db.delete(invite)
    audit(db, user.id, "invite_revoked", "invite", invite_id)
    db.commit()


@router.post("/{user_id}/deactivate", status_code=204)
def deactivate(user_id: int, user: Coordinator, db: Db) -> None:
    if user_id == user.id:
        raise AppError("You cannot deactivate your own account.")
    target = db.get(User, user_id)
    if target is None or target.role != Role.coordinator:
        raise NotFound("That coordinator does not exist.")
    target.is_active = False
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    audit(db, user.id, "coordinator_deactivated", "user", user_id)
    db.commit()
