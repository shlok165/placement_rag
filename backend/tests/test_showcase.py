import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import seed
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
