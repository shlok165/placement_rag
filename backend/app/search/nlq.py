"""Natural-language filters, without an LLM.

"remote ML internship in Bangalore, summer 2027, stipend above 30k" becomes the filters
remote, internship, Bengaluru and a stipend of at least 30,000, plus the clean query
"ML summer 2027". Words that are not filters stay in the query, so nothing the student typed is
thrown away. The student sees each filter as a chip and can remove it before searching.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.search.taxonomy import LOCATION_ALIASES, LOCATIONS, _term_pattern

_AMOUNT = r"(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)*)\s*(k|thousand|lakh|lakhs|lpa|l)?\b"
_STIPEND = re.compile(
    r"\b(?:(?:stipend|pay|paying|salary|ctc)\s*(?:of\s*)?)?(?:above|over|at\s+least|more\s+than|"
    r"min(?:imum)?|>=?|from)\s*" + _AMOUNT + r"(?:\s*(?:/|per|a)\s*(?:month|mo|year|yr))?"
    r"(?:\s*(?:stipend|pay|salary|ctc))?",
    re.IGNORECASE,
)
_STIPEND_PLUS = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)*)\s*(k|lakh|lpa)?\s*\+\s*(?:stipend|pay|salary)?",
    re.IGNORECASE,
)
_NOT_REMOTE = re.compile(
    r"\b(?:no|not|without)\s+(?:remote|wfh|work\s+from\s+home)\b|\bon[- ]?site\b|\bin[- ]office\b",
    re.IGNORECASE,
)
_REMOTE = re.compile(r"\b(?:remote(?!\s+sensing)|wfh|work\s+from\s+home)\b", re.IGNORECASE)
_FULL_TIME = re.compile(
    r"\b(?:full[- ]?time|fte|permanent|job\s+after\s+graduation|placement)\b", re.IGNORECASE
)
_INTERN = re.compile(r"\binter(?:n|nship|nships)\b", re.IGNORECASE)
_CLOSING = (
    (re.compile(r"\b(?:closing|closes|due|deadline)\s+(?:in|within)\s+(\d{1,3})\s+days?\b", re.I),
     None),
    # "Today" becomes one day: the filter counts whole days, and a deadline today is still open.
    (re.compile(r"\b(?:closing|closes|due)\s+today\b", re.I), 1),
    (re.compile(r"\b(?:closing|closes|due)\s+tomorrow\b", re.I), 1),
    (re.compile(r"\b(?:closing|closes|due)\s+this\s+week\b", re.I), 7),
    (re.compile(r"\b(?:closing|closes|due)\s+next\s+week\b", re.I), 14),
    (re.compile(r"\b(?:closing|closes|due)\s+this\s+month\b", re.I), 30),
    (re.compile(r"\bclosing\s+soon\b", re.I), 7),
)  # fmt: skip
_FILLER = re.compile(
    r"\b(?:in|at|near|around|with|and|or|a|an|the|for|of|me|please|show|find|any|some|jobs?|"
    r"roles?|positions?|openings?|opportunit(?:y|ies)|based|located|city|that|which|is|are)\b",
    re.IGNORECASE,
)


@dataclass
class Parsed:
    query: str
    filters: dict[str, Any] = field(default_factory=dict)
    # One per filter, in the order they appeared: (filter key, label for the chip).
    chips: list[dict[str, str]] = field(default_factory=list)


def _amount(number: str, unit: str | None) -> int:
    value = float(number.replace(",", ""))
    unit = (unit or "").lower()
    if unit in ("k", "thousand"):
        value *= 1_000
    elif unit in ("lakh", "lakhs", "lpa", "l"):
        value *= 100_000
    return int(value)


def _cut(text: str, span: tuple[int, int]) -> str:
    return text[: span[0]] + " " * (span[1] - span[0]) + text[span[1] :]


def parse(text: str) -> Parsed:
    work = " ".join(text.split())
    found: list[tuple[int, str, str, Any]] = []

    for pattern in (_STIPEND, _STIPEND_PLUS):
        match = pattern.search(work)
        if match:
            amount = _amount(match.group(1), match.group(2))
            if amount >= 1_000:
                found.append((match.start(), "min_stipend", f"Pay at least ₹{amount:,}", amount))
                work = _cut(work, match.span())
                break

    for pattern, days in _CLOSING:
        match = pattern.search(work)
        if match:
            value = int(match.group(1)) if days is None else days
            label = "Closing by tomorrow" if value == 1 else f"Closing within {value} days"
            found.append((match.start(), "closing_within_days", label, min(value, 365)))
            work = _cut(work, match.span())
            break

    if match := _NOT_REMOTE.search(work):
        found.append((match.start(), "remote", "Not remote", False))
        work = _cut(work, match.span())
    elif match := _REMOTE.search(work):
        found.append((match.start(), "remote", "Remote", True))
        work = _cut(work, match.span())

    if match := _FULL_TIME.search(work):
        found.append((match.start(), "job_type", "Full-time", "full-time"))
        work = _cut(work, match.span())
    elif match := _INTERN.search(work):
        found.append((match.start(), "job_type", "Internship", "internship"))
        work = _cut(work, match.span())
    for match in list(_INTERN.finditer(work)):
        work = _cut(work, match.span())

    places: dict[str, int] = {}
    terms = [*((p.lower(), p) for p in LOCATIONS), *LOCATION_ALIASES.items()]
    for term, canonical in sorted(terms, key=lambda t: -len(t[0])):
        for match in re.finditer(_term_pattern(term), work, re.IGNORECASE):
            places.setdefault(canonical, match.start())
            work = _cut(work, match.span())
    for name, start in places.items():
        found.append((start, "locations", name, name))

    found.sort(key=lambda item: item[0])
    filters: dict[str, Any] = {}
    chips = []
    for _, key, label, value in found:
        if key == "locations":
            filters.setdefault("locations", []).append(value)
        else:
            filters[key] = value
        chips.append({"key": key, "label": label, "value": str(value)})

    query = _FILLER.sub(" ", work)
    query = re.sub(r"[,;:+/|]+", " ", query)
    query = " ".join(w for w in query.split() if w.strip(".-"))
    return Parsed(query=query, filters=filters, chips=chips)
