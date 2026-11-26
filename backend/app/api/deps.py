"""Shared dependencies: database session, current user and role guards."""

import ipaddress
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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


def _trusted(peer: str) -> bool:
    for entry in get_settings().trusted_proxies.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            if peer == entry:
                return True
    return False


def client_ip(request: Request) -> str:
    """The address rate limits are keyed on.

    X-Forwarded-For is written by whoever sends the request, so it is believed only when the
    direct peer is the proxy. Caddy replaces the header with the real client address (it does
    not pass on a client's own header unless that client is a trusted proxy), so its last entry is
    the client. A request that reaches the API directly is keyed on its own peer address, and a
    forged header changes nothing.
    """
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded and _trusted(peer):
        return forwarded.split(",")[-1].strip() or peer
    return peer
