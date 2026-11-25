"""Shared dependencies: database session, current user and role guards."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthenticated
from app.core.security import SESSION_COOKIE, hash_token
from app.db.models import Role, User, UserSession
from app.db.session import get_db

Db = Annotated[Session, Depends(get_db)]

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    now = datetime.now(UTC)
    row = None
    if token:
        row = db.execute(
            select(User, UserSession)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.expires_at > now,
                User.is_active,
            )
        ).first()
    if row is None:
        raise Unauthenticated("Please sign in to continue.")
    user, session = row
    if request.method not in _SAFE_METHODS:
        sent = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(sent, session.csrf_token):
            raise Forbidden(
                "Your session could not be verified. Refresh the page and try again.", code="csrf"
            )
    if user.last_seen_at is None or now - user.last_seen_at > timedelta(minutes=10):
        user.last_seen_at = now
        db.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def coordinator_only(user: CurrentUser) -> User:
    if user.role != Role.coordinator:
        raise Forbidden("This area is for CAPS coordinators only.")
    return user


Coordinator = Annotated[User, Depends(coordinator_only)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # The proxy is the only hop in front of the API, so its entry is the last one.
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
