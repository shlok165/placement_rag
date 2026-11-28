import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import seed
from app.core.config import get_settings
from app.db.models import Announcement, Job, User
from tests.conftest import Api

PASSWORD = "showcase-Pass-2026"


def test_showcase_loads_postings_and_a_demo_student_once(db: Session, anonymous: Api) -> None:
    first = seed.seed_showcase(db, PASSWORD)
    jobs = db.scalar(select(func.count()).select_from(Job))
    seed.seed_showcase(db, PASSWORD)
    assert first["postings"] >= 150
    assert db.scalar(select(func.count()).select_from(Job)) == jobs
    assert db.scalar(select(func.count()).select_from(Announcement)) == 1
    login = {"email": seed.SHOWCASE_STUDENT, "password": PASSWORD}
    assert anonymous.post("/api/auth/login", json=login).status_code == 200


def test_a_deleted_demo_student_comes_back(db: Session) -> None:
    seed.seed_showcase(db, PASSWORD)
    db.execute(delete(User).where(User.email == seed.SHOWCASE_STUDENT))
    db.commit()
    seed.seed_showcase(db, PASSWORD)
    assert db.scalar(select(User.id).where(User.email == seed.SHOWCASE_STUDENT)) is not None


def test_a_weak_demo_password_is_refused(db: Session) -> None:
    with pytest.raises(ValueError):
        seed.seed_showcase(db, "short")


def test_one_click_demo_is_off_unless_switched_on(db: Session, anonymous: Api) -> None:
    seed.seed_showcase(db, PASSWORD)
    assert anonymous.get("/api/auth/demo").json() == {"enabled": False}
    assert anonymous.post("/api/auth/demo").status_code == 404


def test_one_click_demo_signs_in_as_the_demo_student(
    db: Session, anonymous: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "showcase_enabled", True)
    seed.seed_showcase(db, PASSWORD)
    reply = anonymous.post("/api/auth/demo")
    assert reply.status_code == 200
    assert reply.json()["email"] == seed.SHOWCASE_STUDENT
    assert anonymous.get("/api/auth/me").json()["email"] == seed.SHOWCASE_STUDENT


def test_the_demo_account_cannot_be_deleted(
    db: Session, anonymous: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "showcase_enabled", True)
    seed.seed_showcase(db, PASSWORD)
    anonymous.post("/api/auth/demo")
    reply = anonymous.post("/api/profile/delete-account", json={"password": PASSWORD})
    assert reply.status_code == 403
    assert db.scalar(select(User.id).where(User.email == seed.SHOWCASE_STUDENT)) is not None
