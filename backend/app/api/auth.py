from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, Db, client_ip
from app.api.google import enabled as google_enabled
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound, Unauthenticated
from app.core.security import (
    SESSION_COOKIE,
    check_login_delay,
    check_rate_limit,
    clear_attempts,
    end_session,
    hash_password,
    hash_token,
    pair_key,
    record_attempt,
    start_session,
    verify_password,
)
from app.db.audit import audit
from app.db.models import Invite, Role, StudentProfile, User
from app.schemas.auth import AcceptInviteIn, LoginIn, RegisterIn, UserOut
from app.seed import SHOWCASE_STUDENT

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> User:
    address = client_ip(request)
    pair, ip_key = pair_key(body.email, address), f"ip:{address}"
    # One address may not spray many accounts, and one pair slows down after a few misses.
    check_rate_limit(db, ip_key)
    check_login_delay(db, pair)
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(user.password_hash if user else None, body.password):
        record_attempt(db, pair, ip_key)
        raise Unauthenticated(
            "That email and password do not match. Check both and try again.",
            code="bad_credentials",
        )
    assert user is not None
    if not user.is_active:
        raise Forbidden("This account is inactive. Contact the CAPS office.", code="inactive")
    clear_attempts(db, pair)
    start_session(db, user, response)
    return user


@router.get("/demo")
def demo_status() -> dict[str, bool]:
    """Whether this server offers one-click sign-in to the shared demo student."""
    return {"enabled": get_settings().showcase_enabled}


@router.get("/options")
def sign_in_options() -> dict[str, bool]:
    """Which extra ways to sign in this server offers."""
    return {"demo": get_settings().showcase_enabled, "google": google_enabled()}


@router.post("/demo", response_model=UserOut)
def demo_login(request: Request, response: Response, db: Db) -> User:
    """Sign in as the shared demo student, without a password, where the operator allows it."""
    if not get_settings().showcase_enabled:
        raise NotFound("The demo is not available on this server.")
    ip_key = f"ip:demo:{client_ip(request)}"
    check_rate_limit(db, ip_key)
    record_attempt(db, ip_key)
    user = db.scalar(select(User).where(User.email == SHOWCASE_STUDENT, User.is_active))
    if user is None:
        raise NotFound("The demo account is not set up yet.")
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
    # Hashed before the lookup, so an existing address costs the same time as a new one.
    password_hash = hash_password(body.password)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise AppError(
            "We could not create an account with these details. If you already have an "
            "account, sign in or ask the CAPS office to help.",
            code="registration_failed",
        )
    user = User(
        email=body.email,
        password_hash=password_hash,
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
