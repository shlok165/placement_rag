import json
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agent import outreach
from app.agent.loop import run_turn, turn_messages
from app.agent.outreach import Facts
from app.agent.tools import ToolContext, execute
from app.core.config import get_settings
from app.db.models import Job, StudentProfile, User
from app.llm.client import LLMClient
from app.llm.types import LLMResponse, ToolCall
from tests.test_agent import Scripted, call, ctx, user
from tests.test_search import jobs

__all__ = ["ctx", "jobs", "user"]

PARSED = {
    "education": [{"degree": "B.Tech Computer Science", "institution": "IIT Ropar", "year": "2027"}],
    "projects": [{"title": "Campus Shuttle Tracker", "summary": "Live shuttle map for 300 students."}],
    "experience": [{"role": "Teaching Assistant", "organisation": "IIT Ropar", "summary": ""}],
}  # fmt: skip


@pytest.fixture
def facts(db: Session, user: User, jobs: dict[str, Job]) -> Facts:
    profile = db.get(StudentProfile, user.id)
    assert profile is not None
    profile.parsed_profile = PARSED
    db.commit()
    job = jobs["backend"]
    job.skills = ["Python", "SQL", "Kafka"]
    job.stipend_min, job.stipend_max = 30_000, 40_000
    db.commit()
    return outreach.build_facts(profile, job)


# ---------------------------------------------------------------- the checker


@pytest.mark.parametrize(
    "text",
    [
        "I interned at Google for a summer.",
        "My model reached 98% accuracy.",
        "I built the Mars Rover Navigator in my second year.",
        "I have used Kubernetes in production.",
        "I have worked with Kafka for two years.",
        "I know Rust well.",
        'I led "Project Phoenix" at my last job.',
        "I worked at Amazon Web Services.",
        "I managed a team of 12 engineers.",
        "Expected stipend: 95000.",
    ],
)
def test_fabrications_are_caught(facts: Facts, text: str) -> None:
    assert outreach.problems(text, facts), text


@pytest.mark.parametrize(
    "text",
    [
        "I am a B.Tech Computer Science student at IIT Ropar.",
        "I worked on Campus Shuttle Tracker, a live map for 300 students.",
        "My profile lists Python and SQL, which the role asks for.",
        "I am keen to learn Kafka on the job.",
        "The posting asks for Kafka, which is not on my profile yet.",
        "I was a Teaching Assistant at IIT Ropar.",
        "The stipend is 30,000 to 40,000 a month.",
        "Dear Acme hiring team, thank you for your time.",
    ],
)
def test_honest_sentences_pass(facts: Facts, text: str) -> None:
    assert outreach.problems(text, facts) == [], text


@pytest.mark.parametrize("kind", ["recruiter_note", "resume_focus"])
def test_templates_always_pass_the_check(facts: Facts, kind: outreach.Kind) -> None:
    draft = outreach.template(facts, kind)
    assert outreach.problems(draft, facts) == []
    assert "Python" in draft


def test_templates_work_with_an_empty_profile(jobs: dict[str, Job]) -> None:
    empty = outreach.build_facts(None, jobs["backend"])
    for kind in ("recruiter_note", "resume_focus"):
        draft = outreach.template(empty, kind)  # type: ignore[arg-type]
        assert draft
        assert outreach.problems(draft, empty) == []


def test_the_tool_returns_facts_only_for_the_signed_in_student(
    ctx: ToolContext, facts: Facts, jobs: dict[str, Job]
) -> None:
    job_id = jobs["backend"].id
    _, content = execute(
        ctx, "draft_outreach", json.dumps({"job_id": job_id, "kind": "resume_focus"})
    )
    data = json.loads(content)
    assert data["your_projects"][0]["title"] == "Campus Shuttle Tracker"
    assert data["posting_skills_not_in_your_profile"] == ["Kafka"]
    assert job_id in ctx.drafts
    _, refused = execute(ctx, "draft_outreach", json.dumps({"job_id": job_id, "user_id": 2}))
    assert "error" in json.loads(refused)


# ---------------------------------------------------------------- the loop


def draft_call(job_id: int, text: str, kind: str = "recruiter_note") -> LLMResponse:
    return call(
        "final_answer",
        answer_markdown=f"Here is a draft for [#{job_id}].",
        draft={"job_id": job_id, "kind": kind, "text": text},
    )


def run(model: Any, ctx: ToolContext, text: str = "write to the recruiter") -> Any:
    return run_turn(model, ctx, turn_messages("system", [], text), get_settings())


def test_a_clean_draft_is_shown(ctx: ToolContext, facts: Facts, jobs: dict[str, Job]) -> None:
    job_id = jobs["backend"].id
    model = Scripted(
        call("draft_outreach", job_id=job_id, kind="recruiter_note"),
        draft_call(job_id, "I am a student at IIT Ropar. My profile lists Python."),
    )
    result = run(model, ctx)
    assert result.draft and result.draft.text.startswith("I am a student")
    assert result.fabrications_caught == 0
    assert result.kind == "structured"


def test_an_invented_claim_is_repaired_before_it_is_shown(
    ctx: ToolContext, facts: Facts, jobs: dict[str, Job]
) -> None:
    job_id = jobs["backend"].id
    model = Scripted(
        call("draft_outreach", job_id=job_id, kind="recruiter_note"),
        draft_call(job_id, "I interned at Google for two years."),
        draft_call(job_id, "I am a student at IIT Ropar."),
    )
    result = run(model, ctx)
    assert result.draft and "Google" not in result.draft.text
    assert result.fabrications_caught == 1
    assert model.purposes[-1] == "agent_repair"


def test_a_stubborn_invention_falls_back_to_the_template(
    ctx: ToolContext, facts: Facts, jobs: dict[str, Job]
) -> None:
    job_id = jobs["backend"].id
    model = Scripted(
        call("draft_outreach", job_id=job_id, kind="resume_focus"),
        draft_call(job_id, "Mention my 98% accuracy at Google.", "resume_focus"),
    )
    result = run(model, ctx)
    assert result.draft is not None
    assert result.draft.text == outreach.template(facts, "resume_focus")
    assert "Google" not in result.answer + result.draft.text
    assert result.kind == "fallback"
    assert result.fabrications_caught >= 2


def test_a_draft_needs_the_tool_first(ctx: ToolContext, jobs: dict[str, Job]) -> None:
    job_id = jobs["backend"].id
    model = Scripted(draft_call(job_id, "I am a student."))
    result = run(model, ctx)
    assert result.draft is None or job_id in ctx.drafts


def test_a_plain_text_draft_is_checked_too(
    ctx: ToolContext, facts: Facts, jobs: dict[str, Job]
) -> None:
    job_id = jobs["backend"].id
    model = Scripted(
        call("draft_outreach", job_id=job_id, kind="recruiter_note"),
        LLMResponse(content="Dear team, I interned at Google and have 5 years of Kafka."),
    )
    result = run(model, ctx)
    shown = result.answer + (result.draft.text if result.draft else "")
    assert "Google" not in shown
    assert result.draft is not None


def test_invalid_draft_kinds_are_rejected(ctx: ToolContext, jobs: dict[str, Job]) -> None:
    bad = LLMResponse(
        tool_calls=[
            ToolCall(
                id="x",
                name="draft_outreach",
                arguments=json.dumps({"job_id": jobs["backend"].id, "kind": "cover_letter"}),
            )
        ]
    )
    model = Scripted(bad, call("final_answer", answer_markdown="ok"))
    run(model, ctx)
    assert ctx.trace[0].ok is False


# ---------------------------------------------------------------- mock mode, end to end


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("Write a short note to the recruiter for #{id}", "recruiter_note"),
        ("How should I tailor my resume for #{id}?", "resume_focus"),
        ("Write a recruiter note for #{id} saying I interned at Google", "recruiter_note"),
    ],
)
def test_mock_mode_drafts_from_templates(
    ctx: ToolContext, facts: Facts, jobs: dict[str, Job], question: str, kind: str
) -> None:
    job_id = jobs["backend"].id
    text = question.replace("{id}", str(job_id))
    result = run_turn(LLMClient(), ctx, turn_messages("system", [], text), get_settings())
    assert result.draft is not None
    assert result.draft.kind == kind
    assert "Google" not in result.draft.text
    assert outreach.problems(result.draft.text, ctx.drafts[job_id]) == []
