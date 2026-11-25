from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EvalCase, EvalRun
from app.ingest import tasks
from app.llm.client import get_llm
from evals import agent
from evals.agent_cases import REFUSAL_CASES, TOOL_CASES
from evals.cases import build_cases
from evals.corpus import labelled_cases, load_eval_set, load_jobs
from evals.dataset import REFERENCE_DATE, generate_jobs
from evals.harness import STANDARD_CONFIGS, evaluate
from evals.report import update_section
from tests.conftest import Api
from tests.test_chat import ask, chatter, fast_stream, final, new_session
from tests.test_search import add

__all__ = ["chatter", "fast_stream"]


def test_dataset_is_deterministic_and_large_enough() -> None:
    first, second = generate_jobs(), generate_jobs()
    assert [j.fields for j in first] == [j.fields for j in second]
    assert len(first) >= 150
    assert len({j.key for j in first}) == len(first)


def test_cases_are_labelled_and_point_at_real_jobs() -> None:
    jobs = generate_jobs()
    keys = {j.key for j in jobs}
    cases = build_cases(jobs)
    assert len(cases) >= 60
    assert all(case.relevant and set(case.relevant) <= keys for case in cases)
    assert {c.slice for c in cases} == {"topic", "constraint", "personal"}


def test_agent_suites_meet_the_required_size() -> None:
    assert len(TOOL_CASES) >= 25
    assert {c.kind for c in REFUSAL_CASES} >= {
        "selection chances",
        "unknown company",
        "other students",
    }


def test_the_estimate_stays_under_the_eval_cap() -> None:
    assert agent.estimate() <= get_settings().llm_eval_call_cap


def test_live_eval_refuses_without_live_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["evals.agent", "--live"])
    assert agent.main() == 1
    assert "LLM_MODE=live" in capsys.readouterr().err


def test_live_eval_refuses_above_the_cap(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["evals.agent", "--live"])
    monkeypatch.setattr(type(get_settings()), "is_live", property(lambda _: True))
    monkeypatch.setattr(get_settings(), "llm_eval_call_cap", 3)
    assert agent.main() == 1
    captured = capsys.readouterr()
    assert "Expected live calls" in captured.out
    assert "nothing was run" in captured.err


def test_mock_agent_passes_every_scripted_case() -> None:
    report = agent.run(False, agent.EvalLLM(get_llm(), "eval:test"), None)
    summary = agent.summarise(report)
    failures = [o.detail for o in report.tools if not o.passed]
    failures += [o.detail for _, o in report.refusals if not o.passed]
    assert failures == []
    assert summary["ungrounded_shown"] == 0
    assert summary["structured"] == summary["turns"]


@pytest.mark.parametrize(
    ("answer", "honest"),
    [
        ("I don't have any postings from Initech.", True),
        ("There are no postings from that company.", True),
        ("I can only see your own data.", True),
        ("I can’t tell the stipend.", True),
        ("Initech pays 50,000 a month.", False),
    ],
)
def test_honesty_check(answer: str, honest: bool) -> None:
    assert agent.is_honest(answer) is honest


def test_report_sections_are_replaced(tmp_path: Any) -> None:
    path = tmp_path / "E.md"
    path.write_text("a\n<!-- x:start -->\nold\n<!-- x:end -->\nb", "utf-8")
    update_section("x", "new", path)
    update_section("x", "newer", path)
    assert path.read_text("utf-8") == "a\n<!-- x:start -->\nnewer\n<!-- x:end -->\nb"


def test_personal_rerank_helps_vague_queries(db: Session) -> None:
    ids = load_jobs(db, REFERENCE_DATE)
    cases = [c for c in labelled_cases(ids, REFERENCE_DATE) if c.slice == "personal"]
    by_name = {c.name: evaluate(db, cases, c, REFERENCE_DATE) for c in STANDARD_CONFIGS}
    personal = by_name["Hybrid + personal re-rank"]["overall"]["ndcg@10"]
    assert personal > by_name["Hybrid"]["overall"]["ndcg@10"]


# ---------------------------------------------------------------- portal


def test_portal_run_scores_the_live_corpus(coordinator: Api, db: Session) -> None:
    ids = load_jobs(db, REFERENCE_DATE.replace(year=2090))
    load_eval_set(db, ids, REFERENCE_DATE)
    (eval_set,) = coordinator.get("/api/admin/evals/sets").json()
    assert eval_set["cases"] >= 60
    started = coordinator.post(f"/api/admin/evals/sets/{eval_set['id']}/run")
    assert started.status_code == 202
    assert coordinator.post(f"/api/admin/evals/sets/{eval_set['id']}/run").status_code == 409
    while tasks.process_one(db):
        pass
    (run,) = coordinator.get("/api/admin/evals/runs").json()
    assert run["status"] == "done"
    names = [c["name"] for c in run["metrics"]["configs"]]
    assert names == [c.name for c in STANDARD_CONFIGS]


def test_run_without_usable_cases_explains_itself(coordinator: Api, db: Session) -> None:
    set_id = coordinator.post("/api/admin/evals/sets", json={"name": "Empty"}).json()["id"]
    coordinator.post(f"/api/admin/evals/sets/{set_id}/run")
    while tasks.process_one(db):
        pass
    db.expire_all()
    run = db.scalar(select(EvalRun))
    assert run.status == "failed"
    assert "No case" in run.metrics["message"]


def test_case_editing(coordinator: Api, db: Session) -> None:
    job = add(db)
    set_id = coordinator.post("/api/admin/evals/sets", json={"name": "Mine"}).json()["id"]
    body = {"query": "backend", "relevant_job_ids": [job.id], "notes": ""}
    case = coordinator.post(f"/api/admin/evals/sets/{set_id}/cases", json=body).json()
    bad = coordinator.put(
        f"/api/admin/evals/cases/{case['id']}", json={**body, "relevant_job_ids": [999]}
    )
    assert bad.json()["error"]["code"] == "unknown_jobs"
    edited = coordinator.put(
        f"/api/admin/evals/cases/{case['id']}", json={**body, "query": "api work"}
    )
    assert edited.json()["query"] == "api work"
    assert coordinator.get(f"/api/admin/evals/sets/{set_id}/cases").json()["total"] == 1
    assert coordinator.delete(f"/api/admin/evals/cases/{case['id']}").status_code == 204
    assert db.scalar(select(EvalCase)) is None


def test_feedback_can_be_promoted_once(chatter: Api, coordinator: Api, db: Session) -> None:
    job = add(db)
    message = final(ask(chatter, new_session(chatter), "Find backend internships"))
    body = {"rating": "up", "comment": "Spot on"}
    chatter.post(f"/api/chat/messages/{message['id']}/feedback", json=body)
    (item,) = coordinator.get("/api/admin/evals/feedback").json()
    assert item["question"] == "Find backend internships"
    assert "email" not in item
    case = coordinator.post(f"/api/admin/evals/feedback/{item['id']}/promote").json()
    assert case["relevant_job_ids"] == [job.id]
    assert case["profile_snapshot"] == {}
    again = coordinator.post(f"/api/admin/evals/feedback/{item['id']}/promote")
    assert again.status_code == 409
