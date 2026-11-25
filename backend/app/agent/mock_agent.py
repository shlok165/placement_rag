"""A rule-based stand-in for the model. It calls the same tools and obeys the same rules.

It is a pure function of the conversation, so demos and tests are deterministic and cost nothing.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.grounding import MARKER
from app.llm.types import LLMResponse, Message, ToolCall
from app.search.taxonomy import locations_in_text, roles_in_text, skills_in_text

_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "last": -1}
_STAGES = {
    "applied": "applied",
    "interview": "interview",
    "online assessment": "oa",
    "oa": "oa",
    "offer": "offer",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    "withdraw": "withdrawn",
    "interested": "interested",
}
_FILLER = re.compile(
    r"\b(please|can you|could you|show me|show|find me|find|search for|search|list|get me|give me|"
    r"i want|i need|i am looking for|i'm looking for|looking for|suggest|recommend|any|some|are "
    r"there|is there|what|which|me|for me|the|a|an|do you have|tell me about|postings?|openings?|"
    r"opportunities|right now|available)\b",
    re.IGNORECASE,
)


@dataclass
class Turn:
    text: str
    lowered: str
    # Posting ids named by the student, or cited in the last answer ("the second one").
    ids: list[int]
    results: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    final_only: bool = False


def _read(messages: list[Message], tools: list[dict[str, Any]] | None) -> Turn:
    last_user = max(i for i, m in enumerate(messages) if m.get("role") == "user")
    text = str(messages[last_user].get("content") or "")
    lowered = text.lower()
    ids = [
        int(x)
        for x in re.findall(r"#\s?(\d+)|(?:job|posting)\s+(?:id\s+)?(\d+)", lowered)
        for x in x
        if x
    ]
    previous: list[int] = []
    for message in reversed(messages[:last_user]):
        if message.get("role") == "assistant" and MARKER.search(str(message.get("content") or "")):
            previous = [int(x) for x in dict.fromkeys(MARKER.findall(str(message["content"])))]
            break
    if not ids and previous:
        for word, index in _ORDINALS.items():
            if re.search(rf"\b{word}\b", lowered) and -len(previous) <= index < len(previous):
                ids.append(previous[index])
        if not ids and re.search(r"\b(both|them|these two|those two|these|those)\b", lowered):
            ids = previous[:4]
        if not ids and re.search(
            r"\b(it|that one|this one|that job|this job|that role|this role)\b", lowered
        ):
            ids = previous[:1]
    names: dict[str, str] = {}
    results: list[tuple[str, dict[str, Any]]] = []
    for message in messages[last_user + 1 :]:
        for call in message.get("tool_calls") or []:
            names[call["id"]] = call["function"]["name"]
        if message.get("role") == "tool":
            try:
                payload = json.loads(message["content"])
            except ValueError:
                payload = {"error": "unreadable"}
            results.append((names.get(message["tool_call_id"], ""), payload))
    offered = {t["function"]["name"] for t in tools or []}
    return Turn(text, lowered, ids, results, offered == {"final_answer"})


def _call(name: str, **arguments: Any) -> LLMResponse:
    return LLMResponse(
        tool_calls=[
            ToolCall(
                id=f"mock_{name}", name=name, arguments=json.dumps(arguments, ensure_ascii=False)
            )
        ]
    )


def _answer(
    text: str, ids: list[int] | None = None, followups: list[str] | None = None
) -> LLMResponse:
    return _call(
        "final_answer",
        answer_markdown=text,
        cited_job_ids=ids or [],
        suggested_followups=followups or [],
    )


# ---------------------------------------------------------------- request parsing


def _filters(turn: Turn) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    places = locations_in_text(turn.text)
    if places:
        filters["locations"] = places
    if re.search(r"\b(remote|work from home|wfh)\b", turn.lowered) and not re.search(
        r"\b(no|not) remote\b", turn.lowered
    ):
        filters["remote"] = True
    if re.search(r"\bfull[- ]?time\b", turn.lowered):
        filters["job_type"] = "full-time"
    elif re.search(r"\bintern", turn.lowered):
        filters["job_type"] = "internship"
    pay = re.search(
        r"(?:above|over|at least|more than|minimum|min)\s*(?:₹|rs\.?|inr)?\s*(\d[\d,]*)\s*(k)?",
        turn.lowered,
    )
    if pay:
        filters["min_stipend"] = int(pay[1].replace(",", "")) * (1000 if pay[2] else 1)
    return filters


def _query(turn: Turn) -> str:
    text = turn.text
    for place in locations_in_text(text):
        text = re.sub(rf"\b(?:in|at|near|around)?\s*{place}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(remote|work from home|wfh|full[- ]?time|internships?|jobs?|roles?)\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"(?:above|over|at least|more than|minimum|min)\s*(?:₹|rs\.?|inr)?\s*\d[\d,]*\s*k?",
        " ",
        text,
        flags=re.I,
    )
    text = _FILLER.sub(" ", text)
    return " ".join(re.sub(r"[?!.,]", " ", text).split())[:200]


def _days(turn: Turn, default: int = 7) -> int:
    if match := re.search(r"(\d{1,2})\s*day", turn.lowered):
        return int(match[1])
    if match := re.search(r"(\d)\s*week", turn.lowered):
        return int(match[1]) * 7
    if "month" in turn.lowered:
        return 30
    if "tomorrow" in turn.lowered:
        return 1
    return default


def _search(turn: Turn, k: int = 5) -> LLMResponse:
    return _call("search_jobs", query=_query(turn), filters=_filters(turn), k=k)


_NOT_COMPANIES = {
    "Any",
    "Some",
    "Show",
    "Find",
    "Good",
    "I",
    "IIT",
    "CAPS",
    "AI",
    "ML",
    "Is",
    "Does",
    "Are",
    "Do",
    "What",
    "The",
}


def _named_company(text: str) -> str | None:
    pattern = (
        r"\b(?:at|from|by|does|is|has|with)\s+((?:[A-Z][\w&.-]+)(?:\s+[A-Z][\w&.-]+){0,2})"
        r"|\b([A-Z][\w&.-]+(?:\s+[A-Z][\w&.-]+)?)(?:'s)?\s+(?:internships?|jobs?|openings?|roles?|hiring)"
    )
    for match in re.finditer(pattern, text):
        name = (match[1] or match[2] or "").strip(" .?")
        if not name or name in _NOT_COMPANIES:
            continue
        if locations_in_text(name) or skills_in_text(name) or roles_in_text(name):
            continue
        return name
    return None


def _preference_changes(turn: Turn) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if re.search(r"\b(no|not|avoid|without)\s+(remote|work from home)", turn.lowered):
        changes["remote_ok"] = False
    elif re.search(r"\b(remote|work from home)\b", turn.lowered):
        changes["remote_ok"] = True
    places = locations_in_text(turn.text)
    if places:
        changes["locations"] = places
    roles = roles_in_text(turn.text)
    if roles:
        changes["roles"] = roles
    if re.search(r"\bfull[- ]?time\b", turn.lowered):
        changes["job_types"] = ["full-time"]
    elif re.search(r"\bintern", turn.lowered):
        changes["job_types"] = ["internship"]
    if match := re.search(r"(\d{1,2})\s*months?", turn.lowered):
        changes["duration"] = int(match[1])
    pay = re.search(r"(?:stipend|pay)\D{0,20}(\d[\d,]*)\s*(k)?", turn.lowered)
    if pay:
        changes["min_stipend"] = int(pay[1].replace(",", "")) * (1000 if pay[2] else 1)
    return changes


# ---------------------------------------------------------------- answer building


def _line(job: dict[str, Any]) -> str:
    place = job.get("location") or ("Remote" if job.get("remote") else "")
    facts = [place, job.get("pay")]
    days = job.get("days_left")
    if days is not None:
        facts.append("closes today" if days == 0 else f"closes in {days} days")
    if job.get("match_percent") is not None:
        facts.append(f"{job['match_percent']}% match")
    detail = ", ".join(str(f) for f in facts if f)
    return f"**{job['title']}** at {job['company']} [#{job['job_id']}] ({detail})"


def _bullets(jobs: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {_line(j)}" for j in jobs)


def _ids(jobs: list[dict[str, Any]]) -> list[int]:
    return [j["job_id"] for j in jobs]


def _after_search(turn: Turn, found: dict[str, Any]) -> LLMResponse:
    jobs = found.get("results", [])
    company = _named_company(turn.text)
    if company and not any(company.lower() in j["company"].lower() for j in jobs):
        return _answer(
            f"I do not have any postings from {company}. I can only answer from postings that the "
            "CAPS team has published. I can search by role, skill or city instead.",
            followups=["What is closing this week?", "Recommend postings for me"],
        )
    if not jobs or found.get("no_close_match"):
        return _answer(
            "I do not have a posting that closely matches that. Try another role, skill or city.",
            followups=["Recommend postings for me", "What is closing this week?"],
        )
    if company:
        jobs = [j for j in jobs if company.lower() in j["company"].lower()] or jobs
    top = jobs[:4]
    return _answer(
        f"These fit best out of {found.get('total', len(jobs))} matches:\n\n{_bullets(top)}",
        _ids(top),
        [
            f"Why does #{top[0]['job_id']} fit me?",
            "Compare the first two" if len(top) > 1 else "What is closing this week?",
            f"Save #{top[0]['job_id']}",
        ],
    )


def _after_fit(data: dict[str, Any]) -> LLMResponse:
    job = data["job"]
    if data.get("profile_empty"):
        return _answer(
            f"I cannot judge the fit for {_line(job)} because your profile is empty. Add skills "
            "and preferences under Profile.",
            [job["job_id"]],
        )
    parts = [
        f"- {p['part']}: {round(p['value'] * 100)}% ({p['note']})"
        for p in data["parts"]
        if p["value"] is not None
    ]
    missing = ", ".join(data["missing_skills"]) or "nothing listed"
    return _answer(
        f"{_line(job)}\n\n" + "\n".join(parts) + f"\n\nNot in your profile: {missing}. "
        "This compares fit only and says nothing about selection.",
        [job["job_id"]],
        [f"What skills am I missing for #{job['job_id']}?", f"Save #{job['job_id']}"],
    )


def _after_gap(data: dict[str, Any]) -> LLMResponse:
    job = data["job"]
    if data["profile_empty"]:
        return _answer(
            f"Your profile has no skills yet, so I cannot compare it with {_line(job)}.",
            [job["job_id"]],
        )
    has = ", ".join(data["has"]) or "none of the listed skills yet"
    missing = ", ".join(data["missing"])
    tail = f"You are missing: {missing}." if missing else "You have every listed skill."
    return _answer(
        f"For {_line(job)}\n\nYou have: {has}. {tail}",
        [job["job_id"]],
        [f"Why does #{job['job_id']} fit me?", "Find similar roles"],
    )


def _after_compare(data: dict[str, Any]) -> LLMResponse:
    jobs = data["jobs"]
    head = "| | " + " | ".join(f"{j['title']} [#{j['job_id']}]" for j in jobs) + " |"
    rule = "|---|" + "---|" * len(jobs)
    rows = [
        ("Company", "company"),
        ("Location", "location"),
        ("Pay", "pay"),
        ("Deadline", "deadline"),
        ("Match", "match_percent"),
    ]
    lines = []
    for label, key in rows:
        cells = []
        for job in jobs:
            value = job.get(key)
            cells.append(
                "not stated"
                if value is None
                else f"{value}%"
                if key == "match_percent"
                else str(value)
            )
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if any("missing_skills" in j for j in jobs):
        cells = [", ".join(j.get("missing_skills") or []) or "none" for j in jobs]
        lines.append("| Skills to learn | " + " | ".join(cells) + " |")
    return _answer("\n".join([head, rule, *lines]), _ids(jobs), [f"Save #{jobs[0]['job_id']}"])


def _after_deadlines(data: dict[str, Any]) -> LLMResponse:
    mine, others = data["saved_or_tracked"], data["other_closing_soon"]
    parts = []
    if mine:
        parts.append("Saved or tracked by you:\n\n" + _bullets(mine))
    if others:
        parts.append("Also closing soon:\n\n" + _bullets(others))
    if not parts:
        return _answer("Nothing closes in that period.", followups=["What closes this month?"])
    return _answer("\n\n".join(parts), _ids(mine + others), ["Recommend postings for me"])


def _after_profile(data: dict[str, Any]) -> LLMResponse:
    skills = ", ".join(data.get("skills") or []) or "none yet"
    preferences = data.get("preferences") or {}
    roles = ", ".join(preferences.get("roles") or []) or "not set"
    places = ", ".join(preferences.get("locations") or []) or "not set"
    return _answer(
        f"Your profile lists these skills: {skills}. Preferred roles: {roles}. Preferred "
        f"locations: {places}.",
        followups=["Recommend postings for me"],
    )


def _after_job(data: dict[str, Any]) -> LLMResponse:
    job_id = data["job_id"]
    about = data.get("description", "")[:420]
    skills = ", ".join(data.get("skills") or []) or "none listed"
    closed = "" if data.get("open") else "\n\nThis posting is closed."
    return _answer(
        f"{_line(data)}\n\n{about}\n\nSkills: {skills}.{closed}",
        [job_id],
        [f"Why does #{job_id} fit me?", f"What skills am I missing for #{job_id}?"],
    )


# ---------------------------------------------------------------- intents


def _refusal(turn: Turn) -> LLMResponse | None:
    low = turn.lowered
    if re.search(
        r"\b(other|another|different)\s+(student|user|person|people)|\b(my )?(friend|roommate|"
        r"classmate|batchmate|senior)('s|s)?\b|\beveryone'?s\b|\bother students\b|"
        r"\b\w+@\w+|\b(student|user)\s+(id\s+)?\d+",
        low,
    ):
        return _answer(
            "I do not have that. I can only see your own profile, saves and applications, never "
            "another student's.",
            followups=["What does my profile say?", "Recommend postings for me"],
        )
    if re.search(r"\b(ignore|disregard)\b.{0,30}\b(instruction|rule|prompt)|system prompt", low):
        return _answer(
            "I cannot do that. I can help you find, compare and track postings.",
            followups=["Recommend postings for me"],
        )
    if re.search(
        r"\b(chance|chances|probability|odds|likelihood|likely to (get|be)|will i (get|be)|"
        r"guarantee|how likely|cut-?off|acceptance rate|selected)\b",
        low,
    ):
        if turn.ids:
            return None
        return _answer(
            "I do not have data on selection, so I cannot estimate chances. I can show how your "
            "skills and preferences fit a posting instead. Name one with its number.",
            followups=["Recommend postings for me"],
        )
    return None


def _first_step(turn: Turn) -> LLMResponse:
    low = turn.lowered
    refusal = _refusal(turn)
    if refusal:
        return refusal
    if re.search(r"^\s*(hi|hello|hey|thanks|thank you|help)\b[\s!.]*$|what can you do", low):
        return _answer(
            "I can search postings, explain how one fits you, show skill gaps, compare postings, "
            "list deadlines, and prepare saves or tracker updates for you to confirm.",
            followups=["Recommend postings for me", "What is closing this week?"],
        )
    if re.search(r"\b(preference|preferences)\b", low) and re.search(
        r"\b(update|change|set|add|switch|make)\b", low
    ):
        changes = _preference_changes(turn)
        if changes:
            return _call("update_preferences", changes=changes)
        return _answer("Which preference should change: roles, locations, remote, pay or length?")
    if re.search(r"\b(compare|versus|vs\.?)\b", low):
        return _call("compare_jobs", job_ids=turn.ids[:4]) if len(turn.ids) > 1 else _search(turn)
    if re.search(
        r"\b(skill gap|missing|lack|should i learn|need to learn|skills do i need)\b", low
    ):
        return _call("skill_gap", job_id=turn.ids[0]) if turn.ids else _search(turn)
    if re.search(r"\b(chance|chances|probability|odds|likely|selected)\b", low) and turn.ids:
        return _call("explain_fit", job_id=turn.ids[0])
    if turn.ids and re.search(r"\b(fit|fits|suit|suits|match|good for me|right for me|why)\b", low):
        return _call("explain_fit", job_id=turn.ids[0])
    if re.search(
        r"\b(track|mark|log|i applied|i have applied|i've applied|got an? (offer|interview))\b", low
    ):
        stage = next((v for k, v in _STAGES.items() if re.search(rf"\b{k}\b", low)), "interested")
        if turn.ids:
            return _call("track_application", job_id=turn.ids[0], status=stage)
        return _search(turn)
    if re.search(r"\b(save|bookmark)\b", low):
        return _call("save_job", job_id=turn.ids[0]) if turn.ids else _search(turn)
    if re.search(
        r"\b(deadline|deadlines|closing|closes|close|due|expire|expiring|last date)\b", low
    ):
        return _call("list_deadlines", within_days=_days(turn))
    if re.search(r"\bmy (profile|skills|preferences)\b|know about me|about myself", low):
        return _call("get_profile")
    if turn.ids:
        return _call("get_job", job_id=turn.ids[0])
    return _search(turn)


def _next_step(turn: Turn) -> LLMResponse:
    name, data = turn.results[-1]
    if "error" in data:
        return _answer(
            f"I do not have that. {data['error']}", followups=["Recommend postings for me"]
        )
    if name == "search_jobs":
        jobs = data.get("results", [])
        low = turn.lowered
        if len(turn.results) == 1 and jobs and not data.get("no_close_match"):
            top = jobs[0]["job_id"]
            if re.search(r"\b(compare|versus|vs\.?)\b", low) and len(jobs) > 1:
                return _call("compare_jobs", job_ids=_ids(jobs)[:2])
            if re.search(r"\b(skill gap|missing|lack|should i learn|need to learn)\b", low):
                return _call("skill_gap", job_id=top)
            if re.search(r"\b(save|bookmark)\b", low):
                return _call("save_job", job_id=top)
            if re.search(r"\b(track|i applied|i have applied)\b", low):
                stage = "applied" if "applied" in low else "interested"
                return _call("track_application", job_id=top, status=stage)
        return _after_search(turn, data)
    if name == "explain_fit":
        return _after_fit(data)
    if name == "skill_gap":
        return _after_gap(data)
    if name == "compare_jobs":
        return _after_compare(data)
    if name == "list_deadlines":
        return _after_deadlines(data)
    if name == "get_profile":
        return _after_profile(data)
    if name == "get_job":
        return _after_job(data)
    if name == "update_preferences":
        return _answer("I prepared that change. Confirm it below to apply it.")
    job = data["job"]
    if data.get("already_saved"):
        return _answer(f"{_line(job)} is already in your saved list.", [job["job_id"]])
    action = "save it" if name == "save_job" else "update your tracker"
    return _answer(f"{_line(job)}\n\nConfirm below and I will {action}.", [job["job_id"]])


def agent_turn(messages: list[Message], tools: list[dict[str, Any]] | None) -> LLMResponse:
    turn = _read(messages, tools)
    if turn.results:
        return _next_step(turn)
    if turn.final_only:
        return _answer("I do not have an answer for that from the postings.")
    return _first_step(turn)
