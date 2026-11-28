"""Sign in with Google (OpenID Connect, authorization code flow).

Only verified addresses in ALLOWED_EMAIL_DOMAINS are accepted, so a Google sign-in also proves that
the student owns their institute address. A first sign-in creates a student account; an existing
account with the same email (a coordinator, say) is signed in as it is.
"""

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import Db
from app.core.config import get_settings
from app.core.security import start_session
from app.db.models import Role, StudentProfile, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE = "oauth_state"
CALLBACK_PATH = "/api/auth/callback/google"


def _base(request: Request) -> str:
    return (get_settings().public_url or str(request.base_url)).rstrip("/")


def _client() -> httpx.Client:
    """Replaced in tests, which may not reach the network."""
    return httpx.Client(timeout=15)


def enabled() -> bool:
    settings = get_settings()
    return bool(settings.google_client_id and settings.google_client_secret.get_secret_value())


def _fail(code: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?error={code}", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/google")
def start(request: Request) -> RedirectResponse:
    if not enabled():
        return _fail("google_off")
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    domains = sorted(settings.email_domains)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _base(request) + CALLBACK_PATH,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    if len(domains) == 1:
        # A hint for Google's account picker; the domain is checked again below.
        params["hd"] = domains[0]
    response = RedirectResponse(f"{AUTHORIZE}?{urlencode(params)}", status_code=303)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/auth",
    )
    return response


@router.get("/callback/google")
def callback(request: Request, db: Db, code: str = "", state: str = "") -> RedirectResponse:
    expected = request.cookies.get(STATE_COOKIE)
    if not enabled():
        return _fail("google_off")
    if not code or not expected or not secrets.compare_digest(state, expected):
        return _fail("google_state")
    settings = get_settings()
    try:
        with _client() as http:
            token = http.post(
                TOKEN,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret.get_secret_value(),
                    "redirect_uri": _base(request) + CALLBACK_PATH,
                    "grant_type": "authorization_code",
                },
            )
            token.raise_for_status()
            info = http.get(
                USERINFO, headers={"Authorization": f"Bearer {token.json()['access_token']}"}
            )
            info.raise_for_status()
            profile = info.json()
    except (httpx.HTTPError, KeyError, ValueError):
        return _fail("google_failed")

    email = str(profile.get("email") or "").strip().lower()
    if not email or profile.get("email_verified") is not True:
        return _fail("google_unverified")
    if email.rsplit("@", 1)[-1] not in settings.email_domains:
        return _fail("google_domain")

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        name = str(profile.get("name") or email.split("@")[0])[:120]
        # The password can never be used: only Google signs this account in.
        user = User(
            email=email,
            password_hash="!google",
            full_name=name,
            role=Role.student,
        )
        user.profile = StudentProfile()
        db.add(user)
        db.flush()
    elif not user.is_active:
        return _fail("inactive")

    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(STATE_COOKIE, path="/api/auth")
    start_session(db, user, response)
    return response
