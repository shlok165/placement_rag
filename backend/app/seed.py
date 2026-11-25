"""Demo accounts and synthetic postings. The credentials are public and for local demos only."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Role, StudentProfile, User
from app.search.profiles import refresh_embedding
from evals.corpus import load_eval_set, load_jobs

logger = logging.getLogger("app.seed")

DEMO_PASSWORD = "demo-pass-2026"
DEMO_COORDINATOR = "coordinator@example.com"
DEMO_STUDENTS: dict[str, dict[str, Any]] = {
    "asha@example.com": {
        "name": "Asha Demo",
        "skills": ["Python", "SQL", "REST APIs", "Docker", "Git", "React"],
        "preferences": {
            "roles": ["Backend", "Full Stack"],
            "locations": ["Bengaluru", "Pune"],
            "remote_ok": True,
            "job_types": ["internship"],
            "duration": 6,
            "min_stipend": 25_000,
        },
        "parsed": {
            "education": [{"degree": "B.Tech Computer Science", "year": "2027"}],
            "projects": [
                {
                    "title": "Hostel mess planner",
                    "summary": "A web service in Python and SQL that plans weekly menus.",
                }
            ],
            "experience": [],
        },
    },
    # Left without a profile so that the onboarding flow can be demonstrated.
    "ravi@example.com": {"name": "Ravi Demo"},
}


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
    for email, spec in DEMO_STUDENTS.items():
        if not missing(email):
            continue
        user = User(
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=Role.student,
            full_name=spec["name"],
        )
        profile = StudentProfile()
        if "skills" in spec:
            profile.skills = spec["skills"]
            profile.preferences = spec["preferences"]
            profile.parsed_profile = spec["parsed"]
            refresh_embedding(profile)
            user.onboarded_at = user.consent_at = datetime.now(UTC)
        user.profile = profile
        db.add(user)
    db.commit()


def seed_jobs(db: Session) -> None:
    today = datetime.now(UTC).date()
    author = db.scalar(select(User.id).where(User.email == DEMO_COORDINATOR))
    ids = load_jobs(db, today, created_by=author)
    load_eval_set(db, ids, today)
    logger.info("demo data ready", extra={"postings": len(ids)})
