"""Passwords, sessions, CSRF and login rate limiting."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import TooManyRequests
from app.db.models import LoginAttempt, User, UserSession

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"

_hasher = PasswordHasher()
# Verified when the account does not exist, so both paths take the same time.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
    except (VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    lifetime = timedelta(days=settings.session_days)
    now = datetime.now(UTC)
    db.execute(delete(UserSession).where(UserSession.expires_at < now))
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=now + lifetime,
        )
    )
    db.commit()
    max_age = int(lifetime.total_seconds())
    secure = settings.cookie_secure
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="lax"
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=secure, samesite="lax"
    )


def end_session(db: Session, token: str | None, response: Response) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        db.commit()
    clear_cookies(response)


def clear_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


def pair_key(email: str, address: str) -> str:
    return f"pair:{email.lower()}:{address}"


def login_delay(db: Session, key: str, now: datetime | None = None) -> int:
    """Seconds left before this account and address pair may try again.

    The first few failures are free; after that each one doubles the wait, up to a cap. The key is
    the pair, so failures from one address never slow down the same account elsewhere: nobody can
    lock a student out by guessing from their own machine.
    """
    settings = get_settings()
    now = now or datetime.now(UTC)
    since = now - timedelta(minutes=settings.login_window_minutes)
    failures, last = db.execute(
        select(func.count(), func.max(LoginAttempt.created_at)).where(
            LoginAttempt.key_hash == hash_token(key), LoginAttempt.created_at > since
        )
    ).one()
    extra = (failures or 0) - settings.login_free_attempts
    if extra < 0 or last is None:
        return 0
    wait = min(2**extra, settings.login_max_delay_seconds)
    return max(0, int(wait - (now - last).total_seconds() + 0.999))


def check_login_delay(db: Session, key: str) -> None:
    seconds = login_delay(db, key)
    if seconds:
        raise TooManyRequests(
            f"Too many attempts. Please wait {seconds} seconds and try again.",
            code="rate_limited",
            details={"retry_after": seconds},
        )


def check_rate_limit(db: Session, *keys: str) -> None:
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(minutes=settings.login_window_minutes)
    for key in keys:
        count = db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.key_hash == hash_token(key), LoginAttempt.created_at > since)
        )
        # An address is shared by a hostel or lab, so it gets more room than one account.
        limit = settings.login_max_attempts * (5 if key.startswith("ip:") else 1)
        if (count or 0) >= limit:
            raise TooManyRequests(
                f"Too many attempts. Please wait {settings.login_window_minutes} minutes "
                "and try again.",
                code="rate_limited",
            )


def record_attempt(db: Session, *keys: str) -> None:
    since = datetime.now(UTC) - timedelta(days=1)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < since))
    db.add_all(LoginAttempt(key_hash=hash_token(key)) for key in keys)
    db.commit()


def clear_attempts(db: Session, key: str) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == hash_token(key)))
