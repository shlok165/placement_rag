"""Rules-based posting parser. Used in mock mode and when the LLM is unavailable."""

import re
from datetime import date

from app.schemas.jobs import Confidence, ParsedJob
from app.search.taxonomy import (
    canonical_skills,
    locations_in_text,
    skills_in_text,
)

_LABELS: dict[str, tuple[str, ...]] = {
    "company": ("company", "organisation", "organization", "employer", "company name"),
    "title": ("title", "role", "position", "job title", "profile", "designation"),
    "location": ("location", "work location", "place", "based in", "job location"),
    "skills": ("skills", "required skills", "skills required", "tech stack", "key skills"),
    "stipend": ("stipend", "salary", "ctc", "compensation", "pay", "package"),
    "deadline": (
        "deadline",
        "apply by",
        "last date",
        "last date to apply",
        "application deadline",
        "apply before",
        "closes on",
    ),
    "duration": ("duration", "internship duration", "tenure"),
    "apply": ("apply", "apply at", "apply here", "application link", "link", "apply link"),
    "type": ("type", "job type", "employment type", "opportunity type"),
    "requirements": ("requirements", "eligibility", "qualifications", "who can apply"),
    "description": ("description", "about the role", "responsibilities", "job description"),
}
_LABEL_LOOKUP = {name: key for key, names in _LABELS.items() for name in names}
_LABEL_LINE = re.compile(r"^\s*(?:[*•-]\s*)?([A-Za-z][A-Za-z /]{2,28}?)\s*[:\-–]\s+(.+)$")
_HEADING_LINE = re.compile(r"^\s*(?:#+\s*)?([A-Za-z][A-Za-z /]{2,28}?)\s*:?\s*$")

_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ),
        start=1,
    )
    for name in names.split()
}
_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(20\d{2})\b")
_MONTH_DAY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b")

_AMOUNT = r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|lpa|lakhs?|l|lac|crores?|cr)?"
_PAY_RANGE = re.compile(rf"{_AMOUNT}\s*(?:-|–|to)\s*{_AMOUNT}", re.IGNORECASE)
_PAY_ONE = re.compile(_AMOUNT, re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)>\]]+")


def parse_date(text: str) -> date | None:
    def build(year: str, month: int | None, day: str) -> date | None:
        try:
            return date(int(year), month or 0, int(day))
        except ValueError:
            return None

    if m := _ISO.search(text):
        return build(m[1], int(m[2]), m[3])
    if m := _NUMERIC.search(text):
        return build(m[3], int(m[2]), m[1])
    if (m := _DAY_MONTH.search(text)) and m[2].lower() in _MONTHS:
        return build(m[3], _MONTHS[m[2].lower()], m[1])
    if (m := _MONTH_DAY.search(text)) and m[1].lower() in _MONTHS:
        return build(m[3], _MONTHS[m[1].lower()], m[2])
    return None


def _rupees(number: str, unit: str | None) -> int:
    value = float(number.replace(",", ""))
    unit = (unit or "").lower()
    if unit == "k":
        value *= 1_000
    elif unit in ("lpa", "lakh", "lakhs", "l", "lac"):
        value *= 100_000
    elif unit.startswith("cr"):
        value *= 10_000_000
    return int(value)


def parse_pay(text: str) -> tuple[int | None, int | None]:
    """Pay in rupees: monthly for internships, yearly for full-time roles."""
    if m := _PAY_RANGE.search(text):
        unit_low, unit_high = m[2] or m[4], m[4] or m[2]
        low, high = _rupees(m[1], unit_low), _rupees(m[3], unit_high)
        if low >= 1_000 or high >= 1_000:
            return min(low, high), max(low, high)
    if (m := _PAY_ONE.search(text)) and (value := _rupees(m[1], m[2])) >= 1_000:
        return value, value
    return None, None


def parse_duration(text: str) -> int | None:
    if m := re.search(r"(\d{1,2})\s*(?:-|–|to)?\s*\d{0,2}\s*months?", text, re.IGNORECASE):
        return max(1, min(36, int(m[1])))
    if m := re.search(r"(\d{1,3})\s*weeks?", text, re.IGNORECASE):
        return max(1, min(36, round(int(m[1]) / 4.345)))
    return None


def _labelled(text: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    section: str | None = None
    for line in text.splitlines():
        match = _LABEL_LINE.match(line)
        key = _LABEL_LOOKUP.get(match[1].strip().lower()) if match else None
        if match and key:
            found.setdefault(key, []).append(match[2].strip())
            section = key if key in ("requirements", "description", "skills") else None
            continue
        heading = _HEADING_LINE.match(line)
        heading_key = _LABEL_LOOKUP.get(heading[1].strip().lower()) if heading else None
        if heading_key:
            section = heading_key
            continue
        if section and line.strip():
            found.setdefault(section, []).append(line.strip())
        elif not line.strip() and section == "skills":
            section = None
    return {key: "\n".join(lines) for key, lines in found.items()}


_HIRING = re.compile(
    r"([A-Z][\w&.' ]{1,60}?)\s+is\s+(?:hiring|looking for|seeking)\s+(?:an?\s+|for\s+)?"
    r"([A-Z][\w/+&\- ]{3,80}?)(?:\s+(?:in|at|for|to|who|with)\b|[.,\n]|$)"
)
_TITLE_AT = re.compile(
    r"^\s*([A-Z][\w/+&\-() ]{3,80}?)\s+(?:at|@|-|–|\|)\s+([A-Z][\w&.' ]{1,60}?)\s*$", re.MULTILINE
)
_TITLE_WORD = re.compile(
    r"\b(intern|engineer|developer|analyst|designer|scientist|manager|consultant|trainee)\b",
    re.IGNORECASE,
)


def parse_posting(text: str) -> ParsedJob:
    text = text.replace("\r\n", "\n").strip()
    labels = _labelled(text)
    confidence: dict[str, Confidence] = {}

    def note(field: str, value: object, level: Confidence) -> None:
        confidence[field] = level if value not in (None, "", []) else "low"

    company, title = labels.get("company", ""), labels.get("title", "")
    level: Confidence = "high"
    if not (company and title):
        level = "medium"
        if m := _HIRING.search(text):
            company, title = company or m[1].strip(), title or m[2].strip()
        elif (m := _TITLE_AT.search(text)) and _TITLE_WORD.search(m[0]):
            first, second = m[1].strip(), m[2].strip()
            if _TITLE_WORD.search(second) and not _TITLE_WORD.search(first):
                first, second = second, first
            title, company = title or first, company or second
        if not title:
            heading = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            if _TITLE_WORD.search(heading) and len(heading) <= 90:
                title = heading
    note("company", company, "high" if labels.get("company") else level)
    note("title", title, "high" if labels.get("title") else level)

    if labels.get("skills"):
        skills = canonical_skills(re.split(r"[,;\n•|]+", labels["skills"]))
        note("skills", skills, "high")
    else:
        skills = skills_in_text(text)
        note("skills", skills, "medium")

    place = labels.get("location", "")
    remote = bool(
        re.search(r"\b(remote(?!\s+sensing)|work from home|wfh)\b", place or text, re.IGNORECASE)
    )
    if re.search(r"\b(no remote|not remote|on-?site only)\b", text, re.IGNORECASE):
        remote = False
    places = locations_in_text(place or text)
    location = places[0] if places else ("" if remote else place.split(",")[0].strip())
    note("location", location or ("Remote" if remote else ""), "high" if place else "medium")
    confidence["remote"] = "high" if place or remote else "medium"

    kind = labels.get("type", "") + " " + title
    if re.search(r"\bintern", kind, re.IGNORECASE):
        job_type, type_level = "internship", "high"
    elif re.search(r"full[- ]?time|permanent|graduate", kind, re.IGNORECASE):
        job_type, type_level = "full-time", "high"
    elif re.search(r"\b(lpa|ctc)\b", text, re.IGNORECASE):
        job_type, type_level = "full-time", "medium"
    else:
        job_type, type_level = "internship", "medium"
    confidence["job_type"] = type_level  # type: ignore[assignment]

    pay_text = labels.get("stipend", "")
    if not pay_text:
        pay_line = re.search(
            r"[^\n.]*(?:stipend|salary|ctc|lpa|₹|per month)[^\n]*", text, re.IGNORECASE
        )
        pay_text = pay_line[0] if pay_line else ""
    stipend_min, stipend_max = parse_pay(pay_text)
    note("stipend_min", stipend_min, "high" if labels.get("stipend") else "medium")

    deadline = parse_date(labels.get("deadline", ""))
    deadline_level: Confidence = "high"
    if deadline is None:
        deadline_level = "medium"
        near = re.search(r"(?:apply|deadline|last date|before|closes)[^\n]{0,60}", text, re.I)
        deadline = parse_date(near[0]) if near else None
    note("deadline", deadline, deadline_level)

    duration = parse_duration(labels.get("duration", "") or text)
    note("duration_months", duration, "high" if labels.get("duration") else "medium")

    url = _URL.search(labels.get("apply", "")) or _URL.search(text)
    apply_url = url[0].rstrip(".,;") if url else ""
    note("apply_url", apply_url, "high" if labels.get("apply") else "medium")

    requirements = labels.get("requirements", "")
    description = labels.get("description", "") or text
    note("description", description, "high" if labels.get("description") else "medium")
    confidence["requirements"] = "high" if requirements else "medium"

    return ParsedJob(
        company=company[:160],
        title=title[:200],
        description=description[:20_000],
        requirements=requirements[:10_000],
        skills=skills[:40],
        location=location[:120],
        remote=remote,
        job_type=job_type,
        stipend_min=stipend_min,
        stipend_max=stipend_max,
        duration_months=duration,
        deadline=deadline,
        apply_url=apply_url[:500],
        confidence=confidence,
    )
