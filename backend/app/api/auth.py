from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, client_ip
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, Unauthenticated
from app.core.security import (
    SESSION_COOKIE,
    check_rate_limit,
    clear_attempts,
    end_session,
    hash_password,
    hash_token,
    record_attempt,
    start_session,
    verify_password,
)
from app.db.audit import audit
from app.db.models import Invite, Role, StudentProfile, User
from app.schemas.auth import AcceptInviteIn, LoginIn, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> User:
    account_key, ip_key = f"account:{body.email}", f"ip:{client_ip(request)}"
    check_rate_limit(db, account_key, ip_key)
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(user.password_hash if user else None, body.password):
        record_attempt(db, account_key, ip_key)
        raise Unauthenticated(
            "That email and password do not match. Check both and try again.",
            code="bad_credentials",
        )
    assert user is not None
    if not user.is_active:
        raise Forbidden("This account is inactive. Contact the CAPS office.", code="inactive")
    clear_attempts(db, account_key)
    start_session(db, user, response)
    return user


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Db) -> User:
    ip_key = f"ip:register:{client_ip(request)}"
    check_rate_limit(db, ip_key)
    domains = get_settings().email_domains
    if body.email.split("@")[1] not in domains:
        allowed = ", ".join(f"@{d}" for d in sorted(domains))
        raise AppError(
            "Use your institute email to register.",
            code="email_domain",
            details=[{"field": "email", "message": f"Allowed addresses end in {allowed}."}],
        )
    record_attempt(db, ip_key)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise Conflict(
            "An account with this email already exists. Sign in instead.", code="email_taken"
        )
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=Role.student,
    )
    user.profile = StudentProfile()
    db.add(user)
    db.flush()
    start_session(db, user, response)
    return user


@router.post("/accept-invite", response_model=UserOut, status_code=201)
def accept_invite(body: AcceptInviteIn, request: Request, response: Response, db: Db) -> User:
    ip_key = f"ip:invite:{client_ip(request)}"
    check_rate_limit(db, ip_key)
    invite = db.scalar(
        select(Invite).where(Invite.token_hash == hash_token(body.token)).with_for_update()
    )
    now = datetime.now(UTC)
    if invite is None or invite.accepted_at or invite.expires_at < now:
        record_attempt(db, ip_key)
        raise AppError(
            "This invite link is no longer valid. Ask a coordinator for a new one.",
            code="invite_invalid",
        )
    user = db.scalar(select(User).where(User.email == invite.email))
    if user:
        raise Conflict("An account with this email already exists.", code="email_taken")
    user = User(
        email=invite.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=Role.coordinator,
        onboarded_at=now,
    )
    user.profile = StudentProfile()
    db.add(user)
    db.flush()
    invite.accepted_at = now
    audit(db, user.id, "invite_accepted", "user", user.id)
    start_session(db, user, response)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, _: CurrentUser, db: Db) -> None:
    end_session(db, request.cookies.get(SESSION_COOKIE), response)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
