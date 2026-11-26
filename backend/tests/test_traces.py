from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Job
from tests.conftest import Api
from tests.test_chat import ask, chatter, fast_stream, final, new_session
from tests.test_search import jobs

__all__ = ["chatter", "fast_stream", "jobs"]


def answer(client: Api, text: str) -> dict[str, Any]:
    return final(ask(client, new_session(client), text))


def test_only_shared_and_own_turns_are_visible(
    chatter: Api, coordinator: Api, db: Session, jobs: dict[str, Job]
) -> None:
    private = answer(chatter, "Find backend internships")
    shared = answer(chatter, "Find computer vision roles")
    chatter.post(f"/api/chat/messages/{private['id']}/feedback", json={"rating": "up"})
    chatter.post(
        f"/api/chat/messages/{shared['id']}/feedback",
        json={"rating": "down", "comment": "wrong city", "share_trace": True},
    )
    coordinator.post("/api/profile/consent", json={"agreed": True})
    own = answer(coordinator, "What is closing this week?")

    rows = coordinator.get("/api/admin/traces").json()
    assert {r["message_id"]: r["source"] for r in rows} == {
        shared["id"]: "shared",
        own["id"]: "own",
    }
    assert coordinator.get(f"/api/admin/traces/{private['id']}").status_code == 404


def test_a_trace_shows_tools_checks_and_timing(
    chatter: Api, coordinator: Api, db: Session, jobs: dict[str, Job]
) -> None:
    shared = answer(chatter, "Find backend internships")
    chatter.post(
        f"/api/chat/messages/{shared['id']}/feedback", json={"rating": "up", "share_trace": True}
    )
    trace = coordinator.get(f"/api/admin/traces/{shared['id']}").json()
    assert trace["question"] == "Find backend internships"
    assert trace["tools"][0]["name"] == "search_jobs"
    assert trace["tools"][0]["ok"] is True
    assert "ms" in trace["tools"][0]
    assert trace["checks"]["answer_kind"] == "structured"
    assert trace["latency_ms"] >= 0
    assert trace["mode"] == "mock"
    logged = db.scalars(select(AuditLog).where(AuditLog.action == "trace_viewed")).all()
    assert [entry.entity_id for entry in logged] == [str(shared["id"])]


def test_sharing_can_be_withdrawn(chatter: Api, coordinator: Api, jobs: dict[str, Job]) -> None:
    shared = answer(chatter, "Find backend internships")
    url = f"/api/chat/messages/{shared['id']}/feedback"
    chatter.post(url, json={"rating": "up", "share_trace": True})
    assert coordinator.get(f"/api/admin/traces/{shared['id']}").status_code == 200
    chatter.post(url, json={"rating": "up", "share_trace": False})
    assert coordinator.get(f"/api/admin/traces/{shared['id']}").status_code == 404


def test_students_cannot_read_traces(chatter: Api) -> None:
    assert chatter.get("/api/admin/traces").status_code == 403
