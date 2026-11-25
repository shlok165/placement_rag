"""Rules-based resume parser. Runs locally, on redacted text."""

import re

from app.schemas.student import Education, Experience, ParsedProfile, Project
from app.search.taxonomy import canonical_skills, skills_in_text

_SECTIONS: dict[str, tuple[str, ...]] = {
    "education": ("education", "academic background", "academics", "academic qualifications"),
    "skills": ("skills", "technical skills", "skills summary", "technologies", "tools"),
    "projects": ("projects", "academic projects", "personal projects", "key projects"),
    "experience": (
        "experience",
        "work experience",
        "internships",
        "internship experience",
        "professional experience",
    ),
    "other": (
        "achievements",
        "certifications",
        "courses",
        "relevant courses",
        "coursework",
        "positions of responsibility",
        "extracurricular",
        "extra curricular activities",
        "interests",
        "hobbies",
        "summary",
        "objective",
        "references",
        "personal details",
        "declaration",
    ),
}
_HEADINGS = {name: key for key, names in _SECTIONS.items() for name in names}
_DEGREE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\.?|b\.?sc|m\.?sc|ph\.?d|bachelor|master|diploma|class x|"
    r"senior secondary|secondary)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(20\d{2})\s*(?:[-–]|to)\s*(20\d{2}|present|ongoing)\b|\b(20\d{2})\b", re.I)
_BULLET = re.compile(r"^\s*[•●▪◦*\-–]\s*")


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "top"
    for line in text.splitlines():
        heading = re.sub(r"[^a-z ]", "", line.lower()).strip()
        if heading in _HEADINGS and len(line.strip()) <= 40:
            current = _HEADINGS[heading]
            continue
        # "Skills: Python, SQL" carries its content on the same line.
        inline = re.match(r"^\s*([A-Za-z ]{4,30}):\s+(.+)$", line)
        if inline and inline[1].strip().lower() in _HEADINGS:
            key = _HEADINGS[inline[1].strip().lower()]
            sections.setdefault(key, []).append(inline[2])
            continue
        if line.strip():
            sections.setdefault(current, []).append(line.rstrip())
    return sections


def _entries(lines: list[str]) -> list[tuple[str, str]]:
    """Group lines into (heading, details). Bullets belong to the heading above them."""
    entries: list[tuple[str, list[str]]] = []
    for line in lines:
        is_detail = bool(_BULLET.match(line)) or (line[:1].isspace() and bool(entries))
        text = _BULLET.sub("", line).strip()
        if (is_detail and entries) or (entries and not entries[-1][1] and len(text) > 90):
            entries[-1][1].append(text)
        else:
            entries.append((text, []))
    return [(head, " ".join(details)) for head, details in entries if head]


def _year(text: str) -> str:
    match = _YEAR.search(text)
    return match[0] if match else ""


def parse_resume_rules(text: str) -> ParsedProfile:
    sections = _split_sections(text)
    education = [
        Education(
            degree=_YEAR.sub("", line).strip(" ,|-–()")[:200],
            year=_year(line),
        )
        for line in sections.get("education", [])
        if _DEGREE.search(line)
    ][:8]

    listed: list[str] = []
    for line in sections.get("skills", []):
        _, _, after = line.rpartition(":")
        listed += [p.strip() for p in re.split(r"[,;|•●]", after) if 1 <= len(p.strip()) <= 40]
    skills = canonical_skills([*listed, *skills_in_text(text)])[:60]

    projects = [
        Project(title=head.split("|")[0].strip()[:200], summary=detail[:600])
        for head, detail in _entries(sections.get("projects", []))
    ][:12]
    experience = []
    for head, detail in _entries(sections.get("experience", []))[:12]:
        role, _, organisation = _YEAR.sub("", head).partition(" at ")
        if not organisation:
            role, _, organisation = _YEAR.sub("", head).partition(",")
        experience.append(
            Experience(
                role=role.strip(" ,|-–()")[:200],
                organisation=organisation.strip(" ,|-–()")[:200],
                summary=detail[:600],
            )
        )
    return ParsedProfile(
        education=education, skills=skills, projects=projects, experience=experience
    )
