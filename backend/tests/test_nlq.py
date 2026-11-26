from typing import Any

import pytest

from app.search.nlq import parse
from tests.conftest import Api

CASES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "remote ML internship in Bangalore, summer 2027, stipend above 30k",
        "ML summer 2027",
        {"remote": True, "job_type": "internship", "locations": ["Bengaluru"], "min_stipend": 30_000},
    ),
    ("backend internship in Pune", "backend", {"job_type": "internship", "locations": ["Pune"]}),
    ("full-time data engineer in Hyderabad", "data engineer",
     {"job_type": "full-time", "locations": ["Hyderabad"]}),
    ("SDE intern", "SDE", {"job_type": "internship"}),
    ("ML/AI internships", "ML AI", {"job_type": "internship"}),
    ("work from home frontend", "frontend", {"remote": True}),
    ("wfh react developer", "react developer", {"remote": True}),
    ("no remote mechanical design", "mechanical design", {"remote": False}),
    ("on-site civil engineer in New Delhi", "civil engineer", {"remote": False, "locations": ["Delhi"]}),
    ("jobs in Gurgaon or Noida", "", {"locations": ["Gurugram", "Noida"]}),
    ("vlsi roles in bombay", "vlsi", {"locations": ["Mumbai"]}),
    ("stipend at least 25000", "", {"min_stipend": 25_000}),
    ("paying more than ₹40,000 a month", "", {"min_stipend": 40_000}),
    ("data science over 50k per month", "data science", {"min_stipend": 50_000}),
    ("full time ctc above 12 lpa", "", {"job_type": "full-time", "min_stipend": 1_200_000}),
    ("python 20k+ stipend", "python", {"min_stipend": 20_000}),
    ("internships closing this week", "", {"job_type": "internship", "closing_within_days": 7}),
    ("devops closing in 10 days", "devops", {"closing_within_days": 10}),
    ("anything closing tomorrow", "anything", {"closing_within_days": 1}),
    ("roles due today", "", {"closing_within_days": 1}),
    ("product management closing soon", "product management", {"closing_within_days": 7}),
    ("permanent role in Chennai", "", {"job_type": "full-time", "locations": ["Chennai"]}),
    ("computer vision", "computer vision", {}),
    ("remote sensing internship", "remote sensing", {"job_type": "internship"}),
    ("Blockchain intern, remote, Kolkata", "Blockchain",
     {"job_type": "internship", "remote": True, "locations": ["Kolkata"]}),
    ("embedded systems in cochin above 2 lakh", "embedded systems",
     {"locations": ["Kochi"], "min_stipend": 200_000}),
    ("Show me openings for NLP in Mohali", "NLP", {"locations": ["Mohali"]}),
    ("", "", {}),
]  # fmt: skip


@pytest.mark.parametrize(("text", "query", "filters"), CASES)
def test_phrases_become_filters_and_a_clean_query(
    text: str, query: str, filters: dict[str, Any]
) -> None:
    parsed = parse(text)
    assert parsed.filters == filters
    assert parsed.query == query


def test_there_are_enough_phrases() -> None:
    assert len(CASES) >= 25


def test_chips_follow_the_order_typed() -> None:
    chips = parse("in Pune, remote, internship").chips
    assert [c["label"] for c in chips] == ["Pune", "Remote", "Internship"]


def test_small_numbers_are_not_pay() -> None:
    assert "min_stipend" not in parse("over 3 projects").filters


def test_the_endpoint_needs_a_session(anonymous: Api, student: Api) -> None:
    assert anonymous.post("/api/search/parse", json={"text": "x"}).status_code == 401
    reply = student.post("/api/search/parse", json={"text": "remote backend"})
    assert reply.json() == {
        "query": "backend",
        "filters": {"remote": True},
        "chips": [{"key": "remote", "label": "Remote", "value": "True"}],
    }
