"""Test fixtures: a throwaway Postgres database, API clients and a network guard."""

import os

TEST_DB = "placement_test"
_base_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://placement:placement@db:5432/placement"
)
os.environ["DATABASE_URL"] = _base_url.rsplit("/", 1)[0] + f"/{TEST_DB}"
os.environ["LLM_MODE"] = "live" if os.environ.get("RUN_LIVE_LLM") == "1" else "mock"
if os.environ["LLM_MODE"] == "mock":
    # Ordinary test runs never even hold a key.
    for name in [n for n in os.environ if n.startswith(("LLM_API", "LLM_MODEL", "POLLINATIONS_"))]:
        del os.environ[name]
os.environ["RAW_FILES_DIR"] = "/tmp/test-raw"
os.environ["ALLOWED_EMAIL_DOMAINS"] = "iitrpr.ac.in"
os.environ["DEV_EMAIL_DOMAINS"] = "example.com"

from collections.abc import Callable, Iterator

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.security import CSRF_COOKIE, hash_password
from app.db.models import Base, Role, StudentProfile, User
from app.db.session import get_engine, get_sessionmaker
from app.main import app

PASSWORD = "test-pass-2026"
_PASSWORD_HASH = hash_password(PASSWORD)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("RUN_LIVE_LLM") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE_LLM=1 to call the real provider")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    admin = create_engine(_base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    command.upgrade(Config("alembic.ini"), "head")
    yield
    get_engine().dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any real outgoing HTTP request fails the test."""
    if "live" in request.keywords:
        return

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("Tests must not call external services.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    def make(email: str, role: str = Role.student, **kwargs: object) -> User:
        user = User(
            email=email, password_hash=_PASSWORD_HASH, role=role, full_name="Test User", **kwargs
        )
        user.profile = StudentProfile()
        db.add(user)
        db.commit()
        return user

    return make


class Api(TestClient):
    """Test client that sends the CSRF header like the real frontend."""

    def request(self, method: str, url: object, **kwargs: object):  # type: ignore[no-untyped-def,override]
        headers = dict(kwargs.pop("headers", None) or {})  # type: ignore[call-overload]
        if CSRF_COOKIE in self.cookies:
            headers.setdefault("X-CSRF-Token", self.cookies[CSRF_COOKIE])
        return super().request(method, url, headers=headers, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def anonymous() -> Api:
    return Api(app, raise_server_exceptions=False)


@pytest.fixture
def login(make_user: Callable[..., User]) -> Callable[..., Api]:
    def make(email: str, role: str = Role.student, **kwargs: object) -> Api:
        make_user(email, role, **kwargs)
        client = Api(app)
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return client

    return make


@pytest.fixture
def student(login: Callable[..., Api]) -> Api:
    return login("student@example.com")


@pytest.fixture
def coordinator(login: Callable[..., Api]) -> Api:
    return login("coord@example.com", Role.coordinator)
