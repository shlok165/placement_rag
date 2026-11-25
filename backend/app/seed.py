"""Demo accounts. The credentials are public and for local demos only."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Role, StudentProfile, User

logger = logging.getLogger("app.seed")

DEMO_PASSWORD = "demo-pass-2026"
DEMO_COORDINATOR = "coordinator@example.com"
DEMO_STUDENTS = {"asha@example.com": "Asha Demo", "ravi@example.com": "Ravi Demo"}


def create_coordinator(db: Session, email: str, full_name: str, password: str) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=Role.coordinator,
        full_name=full_name,
        onboarded_at=datetime.now(UTC),
    )
    user.profile = StudentProfile()
    db.add(user)
    db.commit()
    return user


def seed_users(db: Session) -> None:
    def missing(email: str) -> bool:
        return db.scalar(select(User.id).where(User.email == email)) is None

    if missing(DEMO_COORDINATOR):
        create_coordinator(db, DEMO_COORDINATOR, "Demo Coordinator", DEMO_PASSWORD)
    for email, name in DEMO_STUDENTS.items():
        if missing(email):
            user = User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                role=Role.student,
                full_name=name,
            )
            user.profile = StudentProfile()
            db.add(user)
    db.commit()
    logger.info("demo accounts ready")
