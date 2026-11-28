from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import google
from app.core.config import get_settings
from app.db.models import Role, User
from tests.conftest import Api


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", SecretStr("not-a-real-secret"))


def fake_google(monkeypatch: pytest.MonkeyPatch, profile: dict[str, Any]) -> list[str]:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token", "id_token": "x"})
        return httpx.Response(200, json=profile)

    monkeypatch.setattr(
        google, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return seen


def start(client: Api) -> str:
    reply = client.get("/api/auth/google", follow_redirects=False)
    assert reply.status_code == 303
    query = parse_qs(urlparse(reply.headers["location"]).query)
    assert query["redirect_uri"][0].endswith("/api/auth/callback/google")
    return query["state"][0]


def test_the_button_is_hidden_until_configured(anonymous: Api) -> None:
    assert anonymous.get("/api/auth/options").json()["google"] is False
    reply = anonymous.get("/api/auth/google", follow_redirects=False)
    assert reply.headers["location"] == "/login?error=google_off"


def test_a_first_sign_in_creates_a_student(
    anonymous: Api, db: Session, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_google(
        monkeypatch,
        {"email": "New.Student@iitrpr.ac.in", "email_verified": True, "name": "New Student"},
    )
    assert anonymous.get("/api/auth/options").json()["google"] is True
    state = start(anonymous)
    reply = anonymous.get(
        f"/api/auth/callback/google?code=abc&state={state}", follow_redirects=False
    )
    assert reply.headers["location"] == "/"
    me = anonymous.get("/api/auth/me").json()
    assert (me["email"], me["role"]) == ("new.student@iitrpr.ac.in", "student")


def test_an_existing_coordinator_signs_in_as_themselves(
    anonymous: Api, make_user: Any, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user("head@iitrpr.ac.in", Role.coordinator)
    fake_google(monkeypatch, {"email": "head@iitrpr.ac.in", "email_verified": True})
    state = start(anonymous)
    anonymous.get(f"/api/auth/callback/google?code=abc&state={state}")
    assert anonymous.get("/api/auth/me").json()["role"] == "coordinator"


@pytest.mark.parametrize(
    ("profile", "error"),
    [
        ({"email": "someone@gmail.com", "email_verified": True}, "google_domain"),
        ({"email": "x@iitrpr.ac.in", "email_verified": False}, "google_unverified"),
    ],
)
def test_other_domains_and_unverified_emails_are_refused(
    anonymous: Api,
    db: Session,
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    profile: dict[str, Any],
    error: str,
) -> None:
    fake_google(monkeypatch, profile)
    state = start(anonymous)
    reply = anonymous.get(
        f"/api/auth/callback/google?code=abc&state={state}", follow_redirects=False
    )
    assert reply.headers["location"] == f"/login?error={error}"
    assert db.scalar(select(User.id).where(User.email == profile["email"])) is None


def test_a_forged_state_is_refused(
    anonymous: Api, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = fake_google(monkeypatch, {"email": "a@iitrpr.ac.in", "email_verified": True})
    start(anonymous)
    reply = anonymous.get("/api/auth/callback/google?code=abc&state=forged", follow_redirects=False)
    assert reply.headers["location"] == "/login?error=google_state"
    assert seen == []


def test_a_google_only_account_has_no_usable_password(
    anonymous: Api, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_google(monkeypatch, {"email": "g@iitrpr.ac.in", "email_verified": True})
    state = start(anonymous)
    anonymous.get(f"/api/auth/callback/google?code=abc&state={state}")
    anonymous.post("/api/auth/logout")
    for guess in ("!google", "", "password"):
        reply = anonymous.post(
            "/api/auth/login", json={"email": "g@iitrpr.ac.in", "password": guess}
        )
        assert reply.status_code in (401, 422)
