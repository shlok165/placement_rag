"""Outreach drafts and the fabrication check.

A draft may only use what the student's profile and the posting say. The check is deterministic:
skills, organisations, projects and numbers in the draft are matched against normalised lists from
those two sources. Anything else is a fabrication, and the draft is not shown.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.db.models import Job, StudentProfile
from app.search.taxonomy import LOCATIONS, canonical_skills, skills_in_text

Kind = Literal["recruiter_note", "resume_focus"]
HOME_INSTITUTION = "IIT Ropar"

# Words that start a capitalised phrase without naming an organisation or a project.
_COMMON = {
    "i", "my", "me", "the", "a", "an", "this", "that", "these", "your", "our", "dear", "hi",
    "hello", "thank", "thanks", "best", "regards", "kind", "sincerely", "team", "hiring",
    "role", "roles", "position", "internship", "intern", "job", "posting", "skills", "skill",
    "projects", "project", "experience", "education", "summary", "put", "lead", "add", "keep",
    "mention", "move", "list", "show", "highlight", "only", "if", "and", "or", "with", "for",
    "at", "in", "on", "to", "of", "from", "it", "is", "are", "was", "be", "as", "by", "you",
    "name", "yours", "b.tech", "m.tech", "btech", "mtech", "phd", "student", "students",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday",
    "remote", "india", "linkedin", "github", "resume", "cv", "please", "would", "could",
    "looking", "keen", "eager", "excited", "here", "draft", "note", "subject", "re",
}  # fmt: skip
# A sentence about wanting to learn something is not a claim to have it.
_ASPIRATION = re.compile(
    r"\b(learn|learning|keen to|eager to|would like to|want to|hope to|excited to|looking "
    r"forward|not yet|grow|develop my|pick up|asks for|lists|requires|mentions|wants|needs|"
    r"does not|doesn't|only if)\b",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i am|i have|my|me)\b", re.IGNORECASE)
_ORG = re.compile(
    r"\b(?:at|with|for|from|joined|interned at|worked at)\s+"
    r"((?:[A-Z][\w&.'-]*)(?:\s+[A-Z][\w&.'-]*){0,4})"
)
_PROJECT = re.compile(
    r"\b(?:project|projects|built|developed|created|designed|made|shipped)\s+(?:called\s+|named\s+|"
    r"on\s+|the\s+)?[\"“']?((?:[A-Z][\w-]*)(?:\s+[A-Z][\w-]*){0,5})"
)
_QUOTED = re.compile(r"[\"“]([^\"”]{3,80})[\"”]")
_NUMBER = re.compile(r"(?<![\w#])(\d[\d,]*(?:\.\d+)?)\s*(%|percent|k\b|lakh|lpa)?", re.IGNORECASE)
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twelve": 12, "hundred": 100, "thousand": 1000,
}  # fmt: skip
_COUNTED = re.compile(
    rf"\b({'|'.join(_NUMBER_WORDS)})\s+(years?|months?|projects?|internships?|users?|students?)\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w+#.& ]", " ", text.lower()).split())


def _numbers(text: str) -> set[float]:
    values: set[float] = set()
    for match in _NUMBER.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        values.add(value)
        unit = (match.group(2) or "").lower()
        if unit == "k":
            values.add(value * 1000)
        elif unit in ("lakh", "lpa"):
            values.add(value * 100_000)
    for match in _COUNTED.finditer(text):
        values.add(float(_NUMBER_WORDS[match.group(1).lower()]))
    return values


@dataclass
class Facts:
    """Everything a draft for one posting may mention."""

    job_id: int
    title: str
    company: str
    student_skills: list[str]
    posting_skills: list[str]
    projects: list[dict[str, str]] = field(default_factory=list)
    experience: list[dict[str, str]] = field(default_factory=list)
    education: list[dict[str, str]] = field(default_factory=list)
    location: str = ""
    numbers: set[float] = field(default_factory=set)

    @property
    def matched_skills(self) -> list[str]:
        mine = {s.lower() for s in self.student_skills}
        return [s for s in self.posting_skills if s.lower() in mine]

    @property
    def missing_skills(self) -> list[str]:
        mine = {s.lower() for s in self.student_skills}
        return [s for s in self.posting_skills if s.lower() not in mine]

    def names(self) -> list[str]:
        """Organisations, places and titles that may be named."""
        items = [self.company, self.title, HOME_INSTITUTION, "IIT", "CAPS", self.location]
        items += [e.get("organisation", "") for e in self.experience]
        items += [e.get("role", "") for e in self.experience]
        items += [e.get("institution", "") for e in self.education]
        items += [e.get("degree", "") for e in self.education]
        items += [p.get("title", "") for p in self.projects]
        items += list(LOCATIONS) + self.student_skills + self.posting_skills
        return [_norm(i) for i in items if i and i.strip()]

    def to_tool(self) -> dict[str, object]:
        return {
            "job": {"job_id": self.job_id, "title": self.title, "company": self.company},
            "your_skills_the_posting_asks_for": self.matched_skills,
            "posting_skills_not_in_your_profile": self.missing_skills,
            "your_projects": self.projects,
            "your_experience": self.experience,
            "your_education": self.education,
            "rules": "Use only these facts. Do not add employers, projects, skills, numbers or "
            "results that are not listed. Put the draft in final_answer.draft.",
        }


def facts_from_tool(data: dict[str, Any]) -> Facts:
    """Facts as draft_outreach returned them, enough for the template."""
    job = data["job"]
    matched = list(data.get("your_skills_the_posting_asks_for") or [])
    missing = list(data.get("posting_skills_not_in_your_profile") or [])
    return Facts(
        job_id=int(job["job_id"]),
        title=str(job["title"]),
        company=str(job["company"]),
        student_skills=matched,
        posting_skills=matched + missing,
        projects=list(data.get("your_projects") or []),
        experience=list(data.get("your_experience") or []),
        education=list(data.get("your_education") or []),
    )


def build_facts(profile: StudentProfile | None, job: Job) -> Facts:
    parsed = (profile.parsed_profile if profile else None) or {}
    projects = [
        {"title": str(p.get("title") or ""), "summary": str(p.get("summary") or "")}
        for p in parsed.get("projects") or []
        if p.get("title")
    ][:5]
    experience = [
        {
            "role": str(e.get("role") or ""),
            "organisation": str(e.get("organisation") or ""),
            "summary": str(e.get("summary") or ""),
        }
        for e in parsed.get("experience") or []
        if e.get("role") or e.get("organisation")
    ][:5]
    education = [
        {
            "degree": str(e.get("degree") or ""),
            "institution": str(e.get("institution") or ""),
            "year": str(e.get("year") or ""),
        }
        for e in parsed.get("education") or []
        if e.get("degree") or e.get("institution")
    ][:3]
    facts = Facts(
        job_id=job.id,
        title=job.title,
        company=job.company,
        student_skills=canonical_skills(profile.skills if profile else []),
        posting_skills=canonical_skills(job.skills),
        projects=projects,
        experience=experience,
        education=education,
        location=job.location or "",
    )
    sources = [job.title, job.description, job.requirements, str(job.stipend_min or ""),
               str(job.stipend_max or ""), str(job.duration_months or "")]  # fmt: skip
    for item in [*projects, *experience, *education]:
        sources += list(item.values())
    facts.numbers = _numbers(" ".join(sources))
    return facts


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _known(name: str, allowed: list[str]) -> bool:
    candidate = _norm(name)
    words = [w for w in candidate.split() if w not in _COMMON]
    if not words:
        return True
    phrase = " ".join(words)
    return any(phrase in item or item in phrase for item in allowed if item)


def problems(text: str, facts: Facts) -> list[str]:
    """What the draft claims that the profile and the posting do not support."""
    found: list[str] = []
    mine = {s.lower() for s in facts.student_skills}
    anywhere = mine | {s.lower() for s in facts.posting_skills}
    # The student's own degree, project and role names are facts, even when they contain
    # words that look like skills ("B.Tech Data Science").
    own = [
        *(e.get("degree", "") for e in facts.education),
        *(p.get("title", "") for p in facts.projects),
        *(e.get("role", "") for e in facts.experience),
    ]
    masked = text
    for phrase in sorted((o for o in own if o.strip()), key=len, reverse=True):
        masked = re.sub(re.escape(phrase), " ", masked, flags=re.IGNORECASE)
    for sentence in _sentences(masked):
        claims = bool(_FIRST_PERSON.search(sentence)) and not _ASPIRATION.search(sentence)
        for skill in skills_in_text(sentence):
            if skill.lower() not in anywhere:
                found.append(f"the skill {skill} is in neither the profile nor the posting")
            elif claims and skill.lower() not in mine:
                found.append(f"it claims {skill}, which is not in the student's profile")
    allowed = facts.names()
    for pattern in (_ORG, _PROJECT, _QUOTED):
        for match in pattern.finditer(text):
            name = match.group(1).strip(" .,;:'\"")
            if not _known(name, allowed):
                found.append(f'"{name}" is not in the profile or the posting')
    for value in sorted(_numbers(text)):
        if value not in facts.numbers:
            shown = int(value) if value.is_integer() else value
            found.append(f"the number {shown} is not in the profile or the posting")
    return list(dict.fromkeys(found))


def template(facts: Facts, kind: Kind) -> str:
    """A draft built only from the facts, used by mock mode and as the fallback."""
    matched, missing = facts.matched_skills, facts.missing_skills
    project = facts.projects[0]["title"] if facts.projects else ""
    degree = facts.education[0]["degree"] if facts.education else ""
    if kind == "recruiter_note":
        study = f"a {degree} student" if degree else "a student"
        lines = [
            f"Dear {facts.company} hiring team,",
            "",
            f"I am {study} at {HOME_INSTITUTION} and I would like to apply for the "
            f"{facts.title} role.",
        ]
        if matched:
            lines.append(f"My profile lists {', '.join(matched[:4])}, which the role asks for.")
        if project:
            lines.append(f"One project I would be glad to talk about is {project}.")
        if missing:
            lines.append(f"I am keen to learn {', '.join(missing[:2])} on the job.")
        lines += ["", "Thank you for your time.", "", "Best regards,", "[Your name]"]
        return "\n".join(lines)
    bullets = []
    if matched:
        bullets.append(f"- Put these skills near the top: {', '.join(matched[:6])}.")
    if project:
        bullets.append(f"- Lead with the project {project}, and say what you built in it.")
    if facts.experience:
        bullets.append(
            f"- Keep your experience as {facts.experience[0]['role'] or 'listed'} close to the top."
        )
    if missing:
        bullets.append(
            f"- The posting also asks for {', '.join(missing[:4])}. Add them only if you really "
            "have them."
        )
    if not bullets:
        bullets.append(
            "- Your profile has little to match yet. Add your skills and projects first."
        )
    return f"Resume focus for {facts.title} at {facts.company}:\n" + "\n".join(bullets)
