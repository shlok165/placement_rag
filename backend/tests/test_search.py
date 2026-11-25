from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, SearchEvent, StudentProfile
from app.ingest.duplicates import hash_text
from app.ingest.indexing import index_job, job_passage
from app.search.config import RerankConfig, get_search_config
from app.search.engine import search, similar_jobs
from app.search.fusion import reciprocal_rank, weighted_sum
from app.search.matching import (
    JobFacts,
    Preferences,
    passes_hard_filters,
    preference_checks,
    role_match,
    skill_overlap,
)
from app.search.profiles import refresh_embedding
from app.search.ranking import Profile, score_job
from app.search.retrieval import Filters, query_terms
from app.search.taxonomy import (
    canonical_location,
    canonical_skills,
    roles_in_text,
    skills_in_text,
)
from evals.metrics import hit_at, ndcg_at, recall_at
from evals.metrics import reciprocal_rank as mrr
from tests.conftest import Api

TODAY = datetime.now(UTC).date()


def add(db: Session, **fields: Any) -> Job:
    base: dict[str, Any] = {
        "company": "Acme",
        "title": "Backend Intern",
        "description": "Build APIs.",
        "skills": ["Python"],
        "location": "Pune",
        "job_type": "internship",
        "deadline": TODAY + timedelta(days=30),
    }
    job = Job(**{**base, **fields}, content_hash=hash_text(repr(sorted(fields.items()))))
    index_job(job)
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def jobs(db: Session) -> dict[str, Job]:
    return {
        "backend": add(db, title="Backend Intern", skills=["Python", "SQL"]),
        "vision": add(
            db,
            title="Computer Vision Intern",
            description="Detect objects in camera images.",
            skills=["Python", "Computer Vision"],
            location="Bengaluru",
        ),
        "civil": add(
            db,
            title="Structural Engineer",
            description="Design bridges and concrete slabs.",
            skills=["STAAD Pro"],
            location="Delhi",
            job_type="full-time",
            stipend_min=900_000,
            stipend_max=1_200_000,
        ),
        "remote": add(
            db,
            title="Frontend Intern",
            description="Build web pages.",
            skills=["React"],
            location="",
            remote=True,
            stipend_min=30_000,
            stipend_max=40_000,
            deadline=TODAY + timedelta(days=2),
        ),
    }


def ids(results: Any) -> list[int]:
    return [h.job.id for h in results.hits]


def test_semantic_search_understands_paraphrase(db: Session, jobs: dict[str, Job]) -> None:
    results = search(db, "teach machines to see pictures", mode="semantic")
    assert ids(results)[0] == jobs["vision"].id


def test_keyword_search_matches_exact_terms(db: Session, jobs: dict[str, Job]) -> None:
    assert ids(search(db, "STAAD bridges", mode="keyword")) == [jobs["civil"].id]


def test_keyword_search_survives_operators_and_quotes(db: Session, jobs: dict[str, Job]) -> None:
    for query in ("a & b | !c", "it's", "back\\slash", "<-> (", "'; DROP TABLE jobs; --", "the of"):
        search(db, query, mode="keyword")
    assert db.scalar(select(Job.id).limit(1)) is not None


def test_rare_terms_outweigh_common_ones(db: Session, jobs: dict[str, Job]) -> None:
    results = search(db, "intern react", mode="keyword")
    assert ids(results)[0] == jobs["remote"].id
    assert query_terms(db, "the internships in") == ["internship"]


def test_hybrid_returns_both_kinds(db: Session, jobs: dict[str, Job]) -> None:
    results = search(db, "python camera")
    assert jobs["vision"].id in ids(results)[:2]
    assert results.top_similarity is not None


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(job_type="full-time"), {"civil"}),
        (Filters(locations=["pune", "Delhi"]), {"backend", "civil"}),
        (Filters(remote=True), {"remote"}),
        (Filters(min_stipend=35_000), {"civil", "remote"}),
        (Filters(closing_within_days=3), {"remote"}),
    ],
)
def test_filters_apply_with_and_without_query(
    db: Session, jobs: dict[str, Job], filters: Filters, expected: set[str]
) -> None:
    wanted = {jobs[name].id for name in expected}
    assert set(ids(search(db, "", filters))) == wanted
    assert set(ids(search(db, "engineer intern web", filters))) <= wanted


@pytest.mark.parametrize("status", ["draft", "pending", "failed", "expired", "archived"])
def test_only_indexed_jobs_are_found(db: Session, jobs: dict[str, Job], status: str) -> None:
    jobs["backend"].status = JobStatus(status)
    db.commit()
    assert jobs["backend"].id not in ids(search(db, "backend python"))
    assert jobs["backend"].id not in ids(search(db, ""))


def test_past_deadline_is_hidden_before_the_nightly_task(db: Session, jobs: dict[str, Job]) -> None:
    db.execute(update(Job).values(deadline=TODAY - timedelta(days=1)))
    db.commit()
    assert ids(search(db, "python")) == []


def test_jobs_without_deadline_stay_open(db: Session) -> None:
    job = add(db, deadline=None)
    assert ids(search(db, "backend")) == [job.id]


def test_sorting_and_paging(db: Session, jobs: dict[str, Job]) -> None:
    by_deadline = search(db, "", sort="deadline", limit=1)
    assert ids(by_deadline) == [jobs["remote"].id]
    assert by_deadline.total == 4
    by_pay = search(db, "", sort="stipend", limit=2)
    assert ids(by_pay) == [jobs["civil"].id, jobs["remote"].id]
    assert len(ids(search(db, "", sort="stipend", limit=2, offset=3))) == 1


def test_personal_ranking_changes_order(db: Session, jobs: dict[str, Job]) -> None:
    civil = Profile(["STAAD Pro"], Preferences(roles=["Civil"], locations=["Delhi"]))
    results = search(db, "", profile=civil)
    assert ids(results)[0] == jobs["civil"].id
    assert results.hits[0].breakdown["matched_skills"] == ["STAAD Pro"]


def test_empty_profile_is_not_personalised(db: Session, jobs: dict[str, Job]) -> None:
    results = search(db, "python", profile=Profile())
    assert results.hits[0].breakdown is None


def test_breakdown_adds_up(db: Session, jobs: dict[str, Job]) -> None:
    config = get_search_config().rerank
    profile = Profile(["Python"], Preferences(locations=["Pune"]))
    detail = score_job(jobs["backend"], profile, config, TODAY, relevance=0.5)
    by_key = {c["key"]: c for c in detail["components"]}
    assert by_key["skills"]["value"] == 0.5
    assert by_key["preferences"]["value"] == 1.0
    assert by_key["profile"]["value"] is None
    fit = (0.5 * config.skills + config.preferences) / (config.skills + config.preferences)
    expected = 0.5 * config.relevance + fit * (config.skills + config.preferences + config.profile)
    assert detail["score"] == pytest.approx(expected, abs=1e-4)
    assert detail["match_percent"] == round(fit * 100)


def test_urgency_only_breaks_ties(db: Session) -> None:
    soon = add(db, title="Backend Intern A", deadline=TODAY + timedelta(days=1))
    later = add(db, title="Backend Intern B", deadline=TODAY + timedelta(days=60))
    config = get_search_config().rerank
    plain = Profile(["Python"])
    assert (
        score_job(soon, plain, config, TODAY)["score"]
        > score_job(later, plain, config, TODAY)["score"]
    )
    smallest = min(config.skills, config.preferences, config.profile, config.relevance)
    assert config.urgency < smallest


def test_config_rejects_loud_urgency() -> None:
    with pytest.raises(ValueError, match="urgency"):
        RerankConfig(relevance=0.4, skills=0.2, preferences=0.2, profile=0.1, urgency=0.3)


def test_config_override_rejects_unknown_keys() -> None:
    with pytest.raises(KeyError):
        get_search_config().override({"fusion.typo": 1})


def test_similar_jobs_exclude_self(db: Session, jobs: dict[str, Job]) -> None:
    found = [j.id for j in similar_jobs(db, jobs["backend"])]
    assert jobs["backend"].id not in found
    assert len(found) == 3


# ---------------------------------------------------------------- pure functions


def test_rrf_rewards_agreement() -> None:
    scores = reciprocal_rank([([(1, 0.9), (2, 0.8)], 1.0), ([(2, 5.0), (3, 1.0)], 1.0)], k=60)
    assert max(scores, key=lambda i: scores[i]) == 2


def test_weighted_sum_scales_each_list() -> None:
    scores = weighted_sum([([(1, 0.9), (2, 0.5)], 1.0), ([(2, 100.0)], 0.5)])
    assert scores == {1: 1.0, 2: 0.5}


def test_metrics() -> None:
    assert hit_at([1, 2, 3], {3}, 2) == 0.0
    assert hit_at([1, 2, 3], {3}, 3) == 1.0
    assert mrr([1, 2, 3], {2}) == 0.5
    assert ndcg_at([1, 2], {1, 2}) == pytest.approx(1.0)
    assert ndcg_at([9, 1], {1}) == pytest.approx(0.6309, abs=1e-4)
    assert recall_at([1, 2, 3], {1, 9}, 3) == 0.5


def test_taxonomy() -> None:
    assert canonical_skills(["postgres", "SQL", " golang ", "k8s"]) == ["SQL", "Go", "Kubernetes"]
    assert canonical_location(" bangalore ") == "Bengaluru"
    assert skills_in_text("Good C++ and React.js; we go fast. Uses REST APIs.") == [
        "C++",
        "React",
        "REST APIs",
    ]
    assert "Go" in skills_in_text("Services in Go and Rust")
    assert roles_in_text("Senior ML Engineer") == ["Machine Learning"]


def test_matching_rules() -> None:
    job = JobFacts(
        "Backend Intern", ["Python", "SQL"], "Pune", False, "internship", 20_000, 30_000, 6
    )
    assert skill_overlap(job.skills, ["sql"]) == (["SQL"], ["Python"])
    assert role_match("Backend Intern", ["Backend"])
    assert not role_match("Backend Intern", ["Civil"])
    prefs = Preferences(
        roles=["Backend"],
        locations=["Pune"],
        job_types=["internship"],
        duration=6,
        min_stipend=25_000,
    )
    assert all(c["met"] for c in preference_checks(job, prefs))
    assert passes_hard_filters(job, prefs)
    assert not passes_hard_filters(job, Preferences(job_types=["full-time"]))
    assert not passes_hard_filters(job, Preferences(locations=["Delhi"]))
    remote = JobFacts("X", [], "", True, "internship")
    assert passes_hard_filters(remote, Preferences(locations=["Delhi"], remote_ok=True))
    assert not passes_hard_filters(remote, Preferences(locations=["Delhi"], remote_ok=False))


# ---------------------------------------------------------------- API


def test_search_api_returns_breakdown_and_logs_anonymously(
    student: Api, db: Session, jobs: dict[str, Job]
) -> None:
    profile = db.scalar(select(StudentProfile))
    profile.skills = ["Python", "SQL"]
    profile.preferences = {"roles": ["Backend"], "locations": ["Pune"]}
    refresh_embedding(profile)
    db.commit()
    body = {"query": "python internship", "personalize": True, "page_size": 2}
    data = student.post("/api/search", json=body).json()
    assert data["personalized"] is True
    assert data["items"][0]["job"]["id"] == jobs["backend"].id
    assert data["items"][0]["breakdown"]["match_percent"] > 80
    assert len(data["items"]) == 2
    event = db.scalar(select(SearchEvent))
    assert event.query == "python internship"
    assert not hasattr(event, "user_id")


def test_search_api_hides_internal_fields(student: Api, jobs: dict[str, Job]) -> None:
    item = student.post("/api/search", json={"query": "backend"}).json()["items"][0]
    assert {"raw_text", "content_hash", "created_by", "embedding"}.isdisjoint(item["job"])


def test_search_api_validates_input(student: Api) -> None:
    assert student.post("/api/search", json={"query": "x" * 301}).status_code == 422
    assert student.post("/api/search", json={"sort": "random"}).status_code == 422


def test_passage_names_company_place_and_skills(jobs: dict[str, Job]) -> None:
    passage = job_passage(jobs["backend"])
    assert passage.startswith("Backend Intern at Acme. Internship in Pune. Skills: Python, SQL.")
