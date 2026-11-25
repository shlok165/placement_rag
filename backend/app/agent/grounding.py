"""Checks an answer before any of it reaches the student."""

import re

from app.agent.schemas import Citation, FinalAnswerArgs

MARKER = re.compile(r"\[#(\d+)\]")
# Other ways a model may write an id. They count as citations too.
_LOOSE = re.compile(
    r"\bjob[_ ]?id\s*[:=#]?\s*(\d+)|\b(?:job|posting)\s*#\s*(\d+)",
    re.IGNORECASE,
)
_PREDICTION = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s?%\s*(?:chance|probability|likelihood|odds)|"
    r"\b(?:chances?|probability|likelihood|odds)\s+(?:of\s+[\w\s]{0,30})?"
    r"(?:is|are|at|around|about)\s+(?:about\s+|around\s+|quite\s+|very\s+)?"
    r"(?:\d|high|low|good|strong|slim|excellent)|"
    r"\byou (?:will|would) (?:definitely|certainly|surely|likely|probably) "
    r"(?:get|be selected|land)|"
    r"\b(?:guarantee|guaranteed)\b[^.]{0,40}\b(?:offer|selection|selected|job|internship)",
    re.IGNORECASE,
)


def mentioned_ids(text: str) -> set[int]:
    ids = {int(m) for m in MARKER.findall(text)}
    for match in _LOOSE.finditer(text):
        ids.add(int(next(g for g in match.groups() if g)))
    return ids


def ungrounded_ids(answer: FinalAnswerArgs, seen: dict[int, Citation]) -> set[int]:
    return (mentioned_ids(answer.answer_markdown) | set(answer.cited_job_ids)) - set(seen)


def predicts_selection(text: str) -> bool:
    return bool(_PREDICTION.search(text))


def problems(answer: FinalAnswerArgs, seen: dict[int, Citation]) -> list[str]:
    found = []
    unknown = ungrounded_ids(answer, seen)
    if unknown:
        listed = ", ".join(str(i) for i in sorted(unknown))
        found.append(f"job_id {listed} did not come from a tool result in this turn")
    if predicts_selection(answer.answer_markdown):
        found.append("the answer predicts selection chances; describe fit factors instead")
    return found


def citations(answer: FinalAnswerArgs, seen: dict[int, Citation]) -> list[Citation]:
    """Cited postings in order of appearance, plus any named without a marker."""
    text = answer.answer_markdown
    ordered = [int(m) for m in MARKER.findall(text)]
    ordered += sorted(mentioned_ids(text) - set(ordered))
    lowered = text.lower()
    for job_id, cited in seen.items():
        if cited.company and cited.company.lower() in lowered and cited.title.lower() in lowered:
            ordered.append(job_id)
    ordered += answer.cited_job_ids
    return [seen[i] for i in dict.fromkeys(ordered) if i in seen]
