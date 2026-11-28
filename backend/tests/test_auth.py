from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.deps import client_ip
from app.core.config import get_settings
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    login_delay,
    pair_key,
    record_attempt,
)
from app.db.models import Invite, User, UserSession
from app.main import app
from tests.conftest import PASSWORD, Api

NEW = {"email": "new@iitrpr.ac.in", "password": "sturdy-pass-1", "full_name": "New Student"}


def test_register_signs_in_and_creates_profile(anonymous: Api) -> None:
    response = anonymous.post("/api/auth/register", json=NEW)
    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert anonymous.get("/api/auth/me").json()["email"] == NEW["email"]


def test_register_rejects_other_domains(anonymous: Api) -> None:
    response = anonymous.post("/api/auth/register", json={**NEW, "email": "a@gmail.com"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "email_domain"


@pytest.mark.parametrize("password", ["short1", "onlyletterslong", "1234567890123"])
def test_register_rejects_weak_passwords(anonymous: Api, password: str) -> None:
    response = anonymous.post("/api/auth/register", json={**NEW, "password": password})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "password"


def test_register_cannot_choose_role(anonymous: Api) -> None:
    response = anonymous.post("/api/auth/register", json={**NEW, "role": "coordinator"})
    assert response.json()["role"] == "student"


def test_duplicate_registration_does_not_say_the_account_exists(
    anonymous: Api, make_user: Callable[..., User]
) -> None:
    make_user(NEW["email"])
    response = anonymous.post("/api/auth/register", json=NEW)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "registration_failed"
    assert "exist" not in error["message"].lower()
    assert SESSION_COOKIE not in response.cookies


def test_duplicate_registration_still_hashes_the_password(
    anonymous: Api, make_user: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user(NEW["email"])
    hashed: list[str] = []
    monkeypatch.setattr("app.api.auth.hash_password", lambda p: hashed.append(p) or "x")
    anonymous.post("/api/auth/register", json=NEW)
    assert hashed == [NEW["password"]]


def test_wrong_password_and_unknown_email_look_the_same(
    anonymous: Api, make_user: Callable[..., User]
) -> None:
    make_user("a@example.com")
    bad = anonymous.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    unknown = anonymous.post("/api/auth/login", json={"email": "b@example.com", "password": "x"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_login_is_rate_limited(anonymous: Api, make_user: Callable[..., User]) -> None:
    make_user("a@example.com")
    for _ in range(8):
        anonymous.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    response = anonymous.post(
        "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
    )
    assert response.status_code == 429


def behind_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat the test client as the proxy, so X-Forwarded-For names the client."""
    monkeypatch.setattr(get_settings(), "trusted_proxies", "testclient")


def test_guesses_from_one_address_do_not_lock_the_owner_out(
    anonymous: Api, make_user: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    behind_proxy(monkeypatch)
    make_user("a@example.com")
    attacker = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(12):
        anonymous.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "x"}, headers=attacker
        )
    blocked = anonymous.post(
        "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}, headers=attacker
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["details"]["retry_after"] > 0
    owner = anonymous.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert owner.status_code == 200


def test_one_address_cannot_spray_many_accounts(
    anonymous: Api, make_user: Callable[..., User], monkeypatch: pytest.MonkeyPatch
) -> None:
    behind_proxy(monkeypatch)
    attacker = {"X-Forwarded-For": "203.0.113.10"}
    statuses = [
        anonymous.post(
            "/api/auth/login",
            json={"email": f"user{i}@example.com", "password": "x"},
            headers=attacker,
        ).status_code
        for i in range(45)
    ]
    assert statuses[:40] == [401] * 40
    assert statuses[-1] == 429


def test_the_delay_doubles_and_then_runs_out(db: Session) -> None:
    settings = get_settings()
    key = pair_key("a@example.com", "203.0.113.1")
    for _ in range(settings.login_free_attempts - 1):
        record_attempt(db, key)
    assert login_delay(db, key) == 0
    record_attempt(db, key)
    assert login_delay(db, key) == 1
    record_attempt(db, key)
    assert login_delay(db, key) == 2
    assert login_delay(db, key, datetime.now(UTC) + timedelta(seconds=5)) == 0
    for _ in range(20):
        record_attempt(db, key)
    assert login_delay(db, key) == settings.login_max_delay_seconds


def request_from(peer: str, forwarded: str | None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_forwarded_for_is_believed_only_from_the_proxy() -> None:
    # Caddy on the Docker network: its header names the client.
    assert client_ip(request_from("172.18.0.5", "198.51.100.7")) == "198.51.100.7"
    # Anyone reaching the API directly cannot pick their own address with a header.
    assert client_ip(request_from("203.0.113.5", "198.51.100.7")) == "203.0.113.5"
    assert client_ip(request_from("203.0.113.5", None)) == "203.0.113.5"
    # Behind the proxy only the last entry counts; earlier ones come from the client.
    assert client_ip(request_from("172.18.0.5", "1.2.3.4, 198.51.100.7")) == "198.51.100.7"


def test_session_cookie_is_http_only(anonymous: Api, make_user: Callable[..., User]) -> None:
    make_user("a@example.com")
    response = anonymous.post(
        "/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}
    )
    cookies = response.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(SESSION_COOKIE))
    assert "HttpOnly" in session
    assert "SameSite=lax" in session


def test_logout_ends_the_session(student: Api, db: Session) -> None:
    token = student.cookies[SESSION_COOKIE]
    assert student.post("/api/auth/logout").status_code == 204
    student.cookies.set(SESSION_COOKIE, token)
    assert student.get("/api/auth/me").status_code == 401
    assert db.scalars(select(UserSession)).all() == []


def test_expired_session_is_rejected(student: Api, db: Session) -> None:
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert student.get("/api/auth/me").status_code == 401


def test_inactive_user_is_rejected(student: Api, db: Session) -> None:
    db.execute(update(User).values(is_active=False))
    db.commit()
    assert student.get("/api/auth/me").status_code == 401


def test_unsafe_request_without_csrf_is_rejected(student: Api) -> None:
    response = student.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf"
    assert CSRF_COOKIE in student.cookies


def _admin_routes() -> list[tuple[str, str]]:
    found = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            found += [(method.upper(), path) for method in operations]
    return found


def _fill(path: str) -> str:
    while "{" in path:
        start, end = path.index("{"), path.index("}")
        path = path[:start] + "1" + path[end + 1 :]
    return path


def test_every_admin_route_rejects_students_and_visitors(student: Api, anonymous: Api) -> None:
    routes = _admin_routes()
    assert routes
    for method, path in routes:
        url = _fill(path)
        assert student.request(method, url).status_code == 403, (method, path)
        assert anonymous.request(method, url).status_code == 401, (method, path)


PUBLIC = {"/healthz", "/readyz", "/metrics"}
PUBLIC |= {"/api/auth/login", "/api/auth/register", "/api/auth/accept-invite"}
# Calendar apps cannot sign in; the secret in the path is checked instead (see test_calendar).
PUBLIC |= {"/api/calendar/feed/{token}.ics"}
# One-click demo sign-in: off unless SHOWCASE_ENABLED, and then rate limited (see test_showcase).
PUBLIC |= {"/api/auth/demo", "/api/auth/options"}
# Google sign-in: a redirect to Google, and its callback, which checks the state cookie.
PUBLIC |= {"/api/auth/google", "/api/auth/callback/google"}


def test_every_other_api_route_needs_a_session(anonymous: Api) -> None:
    for path, operations in app.openapi()["paths"].items():
        if path in PUBLIC:
            continue
        for method in operations:
            response = anonymous.request(method.upper(), _fill(path))
            assert response.status_code == 401, (method, path)


def test_invite_flow(coordinator: Api, anonymous: Api, db: Session) -> None:
    created = coordinator.post("/api/admin/team/invites", json={"email": "c2@example.com"})
    assert created.status_code == 201
    token = created.json()["link"].split("#")[1]
    body = {"token": token, "password": "sturdy-pass-1", "full_name": "Second Coordinator"}
    accepted = anonymous.post("/api/auth/accept-invite", json=body)
    assert accepted.status_code == 201
    assert accepted.json()["role"] == "coordinator"
    assert anonymous.get("/api/admin/team").status_code == 200
    again = Api(app).post("/api/auth/accept-invite", json=body)
    assert again.json()["error"]["code"] == "invite_invalid"
    assert db.scalar(select(Invite)).accepted_at is not None


def test_expired_invite_is_rejected(coordinator: Api, anonymous: Api, db: Session) -> None:
    created = coordinator.post("/api/admin/team/invites", json={"email": "c2@example.com"})
    db.execute(update(Invite).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
    db.commit()
    token = created.json()["link"].split("#")[1]
    body = {"token": token, "password": "sturdy-pass-1", "full_name": "Second Coordinator"}
    assert anonymous.post("/api/auth/accept-invite", json=body).status_code == 400


def test_coordinator_cannot_deactivate_self(coordinator: Api) -> None:
    me = coordinator.get("/api/auth/me").json()
    assert coordinator.post(f"/api/admin/team/{me['id']}/deactivate").status_code == 400
