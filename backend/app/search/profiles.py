"""Build a ranking profile from stored student data."""

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import StudentProfile
from app.embeddings import embed_passages
from app.search.matching import Preferences
from app.search.ranking import Profile


def profile_passage(
    skills: list[str], preferences: dict[str, Any], parsed: dict[str, Any] | None = None
) -> str:
    """Short text that describes the student in the same vocabulary as postings."""
    parsed = parsed or {}
    roles = preferences.get("roles") or []
    parts = [
        f"Looking for roles in {', '.join(roles)}." if roles else "",
        f"Skills: {', '.join(skills)}." if skills else "",
    ]
    for section in ("projects", "experience"):
        for item in (parsed.get(section) or [])[:4]:
            title = str(item.get("title") or item.get("role") or "")
            summary = str(item.get("summary") or "")
            parts.append(f"{title}. {summary}"[:240])
    return " ".join(p for p in parts if p.strip(". "))


def refresh_embedding(profile: StudentProfile) -> None:
    passage = profile_passage(profile.skills, profile.preferences, profile.parsed_profile)
    profile.profile_embedding = embed_passages([passage])[0] if passage else None


def to_ranking_profile(profile: StudentProfile | None) -> Profile:
    if profile is None:
        return Profile()
    vector = profile.profile_embedding
    return Profile(
        skills=list(profile.skills),
        preferences=Preferences.from_dict(profile.preferences),
        embedding=None if vector is None else list(vector),
    )


def load_ranking_profile(db: Session, user_id: int) -> Profile:
    return to_ranking_profile(db.get(StudentProfile, user_id))
