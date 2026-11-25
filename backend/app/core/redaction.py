"""Removes personal identifiers from resume text before it is stored or sent anywhere."""

import re

# Order matters: longer, more specific patterns first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+\s?(?:@|\(at\)|\[at\])\s?[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)),
    (
        "profile link",
        re.compile(
            r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|gitlab\.com|leetcode\.com|"
            r"codeforces\.com|codechef\.com|kaggle\.com|twitter\.com|x\.com|instagram\.com|"
            r"facebook\.com|behance\.net|medium\.com)/[^\s,;|)]+",
            re.IGNORECASE,
        ),
    ),
    ("link", re.compile(r"(?:https?://|www\.)[^\s,;|)]+", re.IGNORECASE)),
    ("date of birth", re.compile(r"(?im)^.*\b(?:date of birth|d\.?o\.?b\.?|born on)\b.*$")),
    (
        "personal detail",
        re.compile(
            r"(?im)^\s*(?:father'?s?|mother'?s?|guardian'?s?|parent'?s?)\s*(?:'s)?\s*name\b.*$|"
            r"^\s*(?:gender|sex|marital status|nationality|religion|caste|category|"
            r"blood group)\s*[:\-].*$"
        ),
    ),
    ("address", re.compile(r"(?im)^.*\b(?:address|residence)\s*[:\-].*$")),
    (
        "address",
        re.compile(
            r"(?im)^.*\b(?:house|flat|h\.?\s?no|plot|street|road|lane|sector|colony|nagar|hostel|"
            r"block|apartment|village|district|tehsil)\b.*\b\d{6}\b.*$"
        ),
    ),
    ("id number", re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b")),
    # Ten to thirteen digits with at most two separators in a row. Year ranges are shorter.
    ("phone", re.compile(r"(?<![\w.])\+?\(?\d(?:[ \t()-]{0,2}\d){9,12}(?!\w)")),
    ("id number", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("id number", re.compile(r"\b20\d{2}[A-Za-z]{2,4}\d{3,5}\b")),
    (
        "id number",
        re.compile(
            r"(?i)\b(?:roll|enrol?lment|registration|entry|aadhaar|aadhar|passport|pan|"
            r"voter id|student id)\s*(?:no|number|id)?\.?\s*[:#\-]?\s*[A-Za-z]*\d[\w/-]{3,}"
        ),
    ),
    ("id number", re.compile(r"\b[A-Z]\d{7}\b|\b\d{9,18}\b")),
]


def redact(text: str, known_names: list[str] | None = None) -> tuple[str, dict[str, int]]:
    """Replace identifiers with labels. Returns the text and a count per kind."""
    counts: dict[str, int] = {}

    def replace(kind: str, pattern: re.Pattern[str], value: str) -> str:
        def mark(_: re.Match[str]) -> str:
            counts[kind] = counts.get(kind, 0) + 1
            return f"[{kind} removed]"

        return pattern.sub(mark, value)

    for kind, pattern in _PATTERNS:
        text = replace(kind, pattern, text)
    for name in known_names or []:
        parts = [p for p in re.split(r"\s+", name.strip()) if len(p) > 2]
        variants = [re.escape(name.strip()).replace(r"\ ", r"\s+")] if name.strip() else []
        variants += [re.escape(p) for p in parts]
        for variant in variants:
            text = replace("name", re.compile(rf"\b{variant}\b", re.IGNORECASE), text)
    return text, counts
