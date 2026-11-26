"""Transparent personal ranking. Every score can be explained from its parts."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from app.db.models import Job
from app.search.config import RerankConfig
from app.search.matching import JobFacts, Preferences, preference_checks, skill_overlap


@dataclass
class Profile:
    """What ranking needs to know about a student."""

    skills: list[str] = field(default_factory=list)
    preferences: Preferences = field(default_factory=Preferences)
    embedding: list[float] | None = None
    # Built from what the student saved, applied to or liked. None when there are no such events.
    taste: list[float] | None = None

    @property
    def is_empty(self) -> bool:
        prefs = self.preferences
        stated = prefs.roles or prefs.locations or prefs.job_types or prefs.min_stipend
        return not (self.skills or stated or self.embedding is not None or self.taste is not None)


def job_facts(job: Job) -> JobFacts:
    return JobFacts(
        title=job.title,
        skills=job.skills,
        location=job.location,
        remote=job.remote,
        job_type=job.job_type,
        stipend_min=job.stipend_min,
        stipend_max=job.stipend_max,
        duration_months=job.duration_months,
    )


def cosine(first: Any, second: Any) -> float:
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / norm if norm else 0.0


def _component(key: str, label: str, value: float | None, weight: float, note: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value": None if value is None else round(value, 4),
        "weight": weight,
        "contribution": 0.0 if value is None else round(value * weight, 4),
        "note": note,
    }


def score_job(
    job: Job, profile: Profile, config: RerankConfig, today: date, relevance: float | None = None
) -> dict[str, Any]:
    """Score one posting for one student and return the full breakdown.

    `relevance` is the normalised search score, or None when there is no query. Parts that cannot
    be judged (no skills listed, no preferences stated) are left out and the rest is rescaled.
    """
    matched, missing = skill_overlap(job.skills, profile.skills)
    skills = len(matched) / len(job.skills) if job.skills and profile.skills else None

    checks = preference_checks(job_facts(job), profile.preferences)
    met = sum(1 for c in checks if c["met"])
    preferences = met / len(checks) if checks else None

    span = config.similarity_ceiling - config.similarity_floor
    closeness = None
    if profile.embedding is not None and job.embedding is not None:
        raw = cosine(profile.embedding, job.embedding)
        closeness = min(1.0, max(0.0, (raw - config.similarity_floor) / span))
    # Only present when there is a taste vector, so without events nothing changes at all.
    taste = None
    if profile.taste is not None and config.taste > 0 and job.embedding is not None:
        raw = cosine(profile.taste, job.embedding)
        taste = min(1.0, max(0.0, (raw - config.similarity_floor) / span))

    urgency = 0.0
    if job.deadline is not None:
        days = (job.deadline - today).days
        if 0 <= days <= config.urgency_window_days:
            urgency = 1 - days / config.urgency_window_days

    fit_parts = [
        _component(
            "skills",
            "Skills",
            skills,
            config.skills,
            f"{len(matched)} of {len(job.skills)} required skills"
            if job.skills
            else "The posting lists no skills",
        ),
        _component(
            "preferences",
            "Preferences",
            preferences,
            config.preferences,
            f"{met} of {len(checks)} preferences" if checks else "No preferences set",
        ),
        _component(
            "profile",
            "Profile match",
            closeness,
            config.profile,
            "How close your profile text is to this posting",
        ),
    ]
    total_weight = config.skills + config.preferences + config.profile
    if taste is not None:
        fit_parts.append(
            _component(
                "taste",
                "Similar to jobs you saved",
                taste,
                config.taste,
                "Close to postings you saved, applied to or liked",
            )
        )
        total_weight += config.taste
    known = [p for p in fit_parts if p["value"] is not None]
    fit_weight = sum(p["weight"] for p in known)
    fit = sum(p["contribution"] for p in known) / fit_weight if fit_weight else None

    total = (fit or 0.0) * total_weight + urgency * config.urgency
    parts = list(fit_parts)
    if relevance is not None:
        total += relevance * config.relevance
        parts.insert(
            0,
            _component(
                "relevance",
                "Search match",
                relevance,
                config.relevance,
                "How well it fits the search",
            ),
        )
    parts.append(
        _component(
            "urgency", "Closing soon", urgency, config.urgency, "A small nudge, never decisive"
        )
    )
    return {
        "score": round(total, 6),
        "match_percent": None if fit is None else round(fit * 100),
        "components": parts,
        "matched_skills": matched,
        "missing_skills": missing,
        "preference_checks": checks,
    }
