"""Deterministic comparison of one posting with one student's profile."""

import re
from dataclasses import dataclass, field

from app.search.taxonomy import ROLES, roles_in_text


@dataclass
class Preferences:
    roles: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    job_types: list[str] = field(default_factory=list)
    duration: int | None = None
    start_window: str = ""
    min_stipend: int | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "Preferences":
        data = data or {}
        return cls(
            roles=list(data.get("roles") or []),
            locations=list(data.get("locations") or []),
            remote_ok=data.get("remote_ok", True) is not False,
            job_types=list(data.get("job_types") or []),
            duration=data.get("duration"),
            start_window=data.get("start_window") or "",
            min_stipend=data.get("min_stipend"),
        )


@dataclass
class JobFacts:
    """The fields matching needs, independent of the ORM."""

    title: str
    skills: list[str]
    location: str
    remote: bool
    job_type: str
    stipend_min: int | None = None
    stipend_max: int | None = None
    duration_months: int | None = None


def skill_overlap(required: list[str], have: list[str]) -> tuple[list[str], list[str]]:
    """Required skills split into matched and missing, in the posting's order."""
    owned = {s.lower() for s in have}
    matched = [s for s in required if s.lower() in owned]
    missing = [s for s in required if s.lower() not in owned]
    return matched, missing


def role_match(title: str, roles: list[str]) -> bool:
    lowered = title.lower()
    families = set(roles_in_text(title))
    for role in roles:
        if role in families:
            return True
        if role not in ROLES:
            words = [w for w in re.findall(r"[a-z+#]+", role.lower()) if len(w) > 2]
            if words and all(w in lowered for w in words):
                return True
    return False


def location_match(job: JobFacts, prefs: Preferences) -> bool:
    if job.remote and prefs.remote_ok:
        return True
    if not prefs.locations:
        return bool(job.location) or prefs.remote_ok
    wanted = {loc.lower() for loc in prefs.locations}
    return job.location.lower() in wanted


def preference_checks(job: JobFacts, prefs: Preferences) -> list[dict[str, object]]:
    """One row per preference the student has stated. Unstated ones are left out."""
    checks: list[dict[str, object]] = []

    def add(key: str, label: str, met: bool) -> None:
        checks.append({"key": key, "label": label, "met": met})

    if prefs.roles:
        add("role", f"Role: {', '.join(prefs.roles[:3])}", role_match(job.title, prefs.roles))
    if prefs.locations:
        place = "Remote" if job.remote and not job.location else job.location or "not stated"
        add("location", f"Location: {place}", location_match(job, prefs))
    elif not prefs.remote_ok:
        add("location", "On-site role", not job.remote or bool(job.location))
    if prefs.job_types:
        add("job_type", f"Type: {job.job_type}", job.job_type in prefs.job_types)
    if prefs.duration and job.duration_months and job.job_type == "internship":
        fits = abs(job.duration_months - prefs.duration) <= 1
        add("duration", f"Duration: {job.duration_months} months", fits)
    if prefs.min_stipend and job.job_type == "internship":
        top = job.stipend_max or job.stipend_min
        if top is not None:
            add("stipend", f"Stipend up to ₹{top:,} a month", top >= prefs.min_stipend)
    return checks


def passes_hard_filters(job: JobFacts, prefs: Preferences) -> bool:
    """Used for alerts: never notify about a place or job type the student ruled out."""
    if prefs.job_types and job.job_type not in prefs.job_types:
        return False
    if prefs.locations:
        return location_match(job, prefs)
    return prefs.remote_ok or bool(job.location) or not job.remote
