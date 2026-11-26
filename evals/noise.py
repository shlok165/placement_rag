"""Deterministic noise for the messy-text slice: typos, abbreviations, odd case, boilerplate.

The same posting always gets the same noise. Labels are taken from the clean posting.
"""

import random
import re
from dataclasses import replace

from evals.dataset import SyntheticJob

# Shorthand seen in real postings, applied to titles and descriptions.
ABBREVIATIONS = (
    ("Machine Learning", "ML/AI"),
    ("Artificial Intelligence", "AI"),
    ("Software Development Engineer", "SDE"),
    ("Backend Engineering", "SDE"),
    ("Full Stack", "FS"),
    ("Computer Vision", "CV"),
    ("Data Science", "DS"),
    ("Developer", "Dev"),
    ("Engineering", "Engg"),
    ("Engineer", "Engr"),
    ("Management", "Mgmt"),
    ("Research", "R&D"),
    ("Associate", "Assoc."),
    ("Internship", "Intrnship"),
    ("Intern", "intern"),
    ("and", "&"),
    ("with", "w/"),
)
SKILL_SHORTHAND = {
    "JavaScript": "JS",
    "TypeScript": "TS",
    "Machine Learning": "ML",
    "Deep Learning": "DL",
    "Computer Vision": "CV",
    "Kubernetes": "k8s",
    "REST APIs": "rest api",
    "Natural Language Processing": "NLP",
    "Data Visualization": "dataviz",
    "Embedded Systems": "embedded",
    "Product Management": "PM",
    "Control Systems": "controls",
}
OPENERS = (
    "**URGENT HIRING** Apply ASAP!!!",
    "Hiring now - limited seats.",
    "#hiring #internship #freshers",
)
CLOSER = (
    "We are an equal opportunity employer. Shortlisted candidates will be contacted by email. "
    "Terms and conditions apply. Please share this post with your friends!!"
)


def _abbreviate(text: str) -> str:
    for long, short in ABBREVIATIONS:
        text = re.sub(rf"\b{re.escape(long)}\b", short, text)
    return text


def _typo(word: str, rng: random.Random) -> str:
    if len(word) < 5 or not word.isalpha():
        return word
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2 :]


def _case(text: str, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.25:
        return text.upper()
    if roll < 0.5:
        return text.lower()
    return text


def noisy(job: SyntheticJob) -> SyntheticJob:
    rng = random.Random(f"noise:{job.key}")
    fields = dict(job.fields)
    fields["title"] = _case(_abbreviate(fields["title"]), rng)
    words = [
        _typo(w, rng) if rng.random() < 0.12 else w
        for w in _abbreviate(fields["description"]).split(" ")
    ]
    body = " ".join(words)
    if rng.random() < 0.3:
        body = body.lower()
    opener = rng.choice(OPENERS) + " " if rng.random() < 0.6 else ""
    fields["description"] = f"{opener}{body} {CLOSER}"
    fields["skills"] = [
        SKILL_SHORTHAND.get(s, s.lower() if rng.random() < 0.3 else s) for s in fields["skills"]
    ]
    return replace(job, fields=fields)
