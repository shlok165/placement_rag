import json
import threading
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import service
from app.core.config import get_settings
from app.db.models import (
    ChatMessage,
    LlmCall,
    MemoryFact,
    PendingAction,
    SavedJob,
    StudentProfile,
)
from tests.conftest import Api
from tests.test_search import add


@pytest.fixture(autouse=True)
def fast_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "CHUNK_PAUSE_S", 0.0)
    original = service.answer_message
    monkeypatch.setattr(
        service, "answer_message", lambda *args, **kwargs: original(*args, pause=0.0, **kwargs)
    )


@pytest.fixture
def chatter(login: Callable[..., Api]) -> Api:
    client = login("student@example.com")
    client.post("/api/profile/consent", json={"agreed": True})
    return client


def new_session(client: Api) -> int:
    return int(client.post("/api/chat/sessions").json()["id"])


def ask(client: Api, session_id: int, text: str) -> list[dict[str, Any]]:
    response = client.post(f"/api/chat/sessions/{session_id}/messages", json={"text": text})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = [x for x in response.text.split("\n\n") if x.startswith("data: ")]
    return [json.loads(x[6:]) for x in lines]


def final(events: list[dict[str, Any]]) -> dict[str, Any]:
    assert events[-1]["type"] == "done", events[-1]
    return events[-1]["message"]


def test_consent_is_required(student: Api) -> None:
    session_id = new_session(student)
    response = student.post(f"/api/chat/sessions/{session_id}/messages", json={"text": "hi"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "consent_required"


def test_answer_streams_with_status_citations_and_followups(chatter: Api, db: Session) -> None:
    job = add(db, title="Backend Intern", skills=["Python"])
    events = ask(chatter, new_session(chatter), "Find backend internships")
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status"
    assert "delta" in kinds
    message = final(events)
    assert "".join(e["text"] for e in events if e["type"] == "delta") == message["content"]
    assert message["citations"] == [
        {"job_id": job.id, "title": "Backend Intern", "company": "Acme"}
    ]
    assert message["suggested_followups"]


def test_history_is_stored_and_titled(chatter: Api, db: Session) -> None:
    add(db)
    session_id = new_session(chatter)
    ask(chatter, session_id, "Find backend internships")
    ask(chatter, session_id, "Why does the first one fit me?")
    messages = chatter.get(f"/api/chat/sessions/{session_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert chatter.get("/api/chat/sessions").json()[0]["title"] == "Find backend internships"
    tools = db.scalars(select(ChatMessage.tool_calls).order_by(ChatMessage.id)).all()
    assert [t[0]["name"] for t in tools if t] == ["search_jobs", "explain_fit"]


def test_write_actions_wait_for_confirmation(chatter: Api, db: Session) -> None:
    job = add(db)
    message = final(ask(chatter, new_session(chatter), f"Save #{job.id}"))
    (action,) = message["pending_actions"]
    assert action["label"] == "Save Backend Intern at Acme"
    assert db.scalar(select(func.count()).select_from(SavedJob)) == 0
    done = chatter.post(f"/api/chat/actions/{action['id']}/confirm").json()
    assert done["status"] == "confirmed"
    assert db.scalar(select(func.count()).select_from(SavedJob)) == 1
    again = chatter.post(f"/api/chat/actions/{action['id']}/confirm")
    assert again.status_code == 409


def test_rejected_actions_change_nothing(chatter: Api, db: Session) -> None:
    job = add(db)
    message = final(ask(chatter, new_session(chatter), f"Track #{job.id} as applied"))
    action = message["pending_actions"][0]
    chatter.post(f"/api/chat/actions/{action['id']}/reject")
    assert chatter.get("/api/applications").json() == []


def test_confirmed_tracking_and_preferences(chatter: Api, db: Session) -> None:
    job = add(db)
    session_id = new_session(chatter)
    tracked = final(ask(chatter, session_id, f"Track #{job.id} as interview"))
    chatter.post(f"/api/chat/actions/{tracked['pending_actions'][0]['id']}/confirm")
    assert chatter.get("/api/applications").json()[0]["status"] == "interview"
    chatter.put("/api/profile/preferences", json={"roles": ["Backend"], "locations": ["Pune"]})
    changed = final(ask(chatter, session_id, "Change my preferences to Delhi and no remote"))
    chatter.post(f"/api/chat/actions/{changed['pending_actions'][0]['id']}/confirm")
    preferences = chatter.get("/api/profile").json()["preferences"]
    assert preferences["locations"] == ["Delhi"]
    assert preferences["remote_ok"] is False
    assert preferences["roles"] == ["Backend"]
    assert db.scalar(select(StudentProfile.profile_embedding)) is not None


def test_memory_is_proposed_confirmed_used_edited_and_deleted(chatter: Api, db: Session) -> None:
    add(db)
    session_id = new_session(chatter)
    message = final(ask(chatter, session_id, "I'm targeting summer 2027. Find backend roles"))
    (action,) = [a for a in message["pending_actions"] if a["kind"] == "remember"]
    assert chatter.get("/api/memory").json() == []
    chatter.post(f"/api/chat/actions/{action['id']}/confirm")
    (fact,) = chatter.get("/api/memory").json()
    assert fact["text"] == "Targeting summer 2027"
    again = final(ask(chatter, session_id, "I'm targeting summer 2027"))
    assert [a for a in again["pending_actions"] if a["kind"] == "remember"] == []
    edited = chatter.put(f"/api/memory/{fact['id']}", json={"text": "Targeting winter 2027"})
    assert edited.json()["text"] == "Targeting winter 2027"
    assert chatter.delete(f"/api/memory/{fact['id']}").status_code == 204
    assert chatter.get("/api/memory").json() == []


def test_memory_reaches_the_next_prompt(
    chatter: Api, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = chatter.get("/api/auth/me").json()["id"]
    db.add(MemoryFact(user_id=user_id, text="No on-site roles"))
    db.commit()
    prompts: list[str] = []
    original = service.turn_messages

    def spy(system: str, history: Any, text: str) -> Any:
        prompts.append(system)
        return original(system, history, text)

    monkeypatch.setattr(service, "turn_messages", spy)
    ask(chatter, new_session(chatter), "hello")
    assert "No on-site roles" in prompts[0]


def test_no_memory_call_when_nothing_is_personal(chatter: Api, db: Session) -> None:
    add(db)
    ask(chatter, new_session(chatter), "Find backend internships")
    purposes = set(db.scalars(select(LlmCall.purpose)))
    assert purposes == {"agent_turn"}


def test_old_messages_become_a_summary(chatter: Api, db: Session) -> None:
    add(db)
    session_id = new_session(chatter)
    for index in range(6):
        ask(chatter, session_id, f"Find backend internships round {index}")
    db.expire_all()
    from app.db.models import ChatSession

    summary = db.get(ChatSession, session_id).summary
    assert "round 0" in summary
    assert "Postings discussed" in summary


def test_quota_blocks_and_is_reported(chatter: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "student_daily_turns", 2)
    session_id = new_session(chatter)
    ask(chatter, session_id, "hello")
    status = chatter.get("/api/chat/status").json()
    assert status["quota"] == {"limit": 2, "used": 1, "remaining": 1}
    ask(chatter, session_id, "hello")
    blocked = chatter.post(f"/api/chat/sessions/{session_id}/messages", json={"text": "hi"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "quota"


def test_stop_keeps_only_what_was_shown(chatter: Api, db: Session) -> None:
    add(db)
    session_id = new_session(chatter)
    user_id = chatter.get("/api/auth/me").json()["id"]
    session = service.owned_session(db, user_id, session_id)
    message = service.start_message(db, session, "Find backend internships and save one")
    cancel = threading.Event()
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if event["type"] == "delta":
            cancel.set()

    service.answer_message(user_id, session_id, message.id, emit, cancel)
    reply = final(events)
    assert reply["stopped"] is True
    assert reply["content"] == events[-2]["text"]
    assert reply["pending_actions"] == []
    assert db.scalar(select(func.count()).select_from(PendingAction)) == 0


def test_failures_are_reported_in_plain_language(
    chatter: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("secret stack detail")

    monkeypatch.setattr(service, "run_turn", broken)
    events = ask(chatter, new_session(chatter), "hello")
    assert events[-1]["type"] == "error"
    assert "secret" not in events[-1]["message"]


def test_feedback(chatter: Api, db: Session) -> None:
    session_id = new_session(chatter)
    message = final(ask(chatter, session_id, "hello"))
    url = f"/api/chat/messages/{message['id']}/feedback"
    assert chatter.post(url, json={"rating": "down", "comment": "too short"}).status_code == 204
    assert chatter.post(url, json={"rating": "up"}).status_code == 204
    stored = chatter.get(f"/api/chat/sessions/{session_id}/messages").json()
    assert stored[-1]["feedback"] == "up"
    assert chatter.post(url, json={"rating": "meh"}).status_code == 422


def test_conversations_are_private(chatter: Api, login: Any, db: Session) -> None:
    job = add(db)
    session_id = new_session(chatter)
    message = final(ask(chatter, session_id, f"I prefer Pune. Save #{job.id}"))
    other = login("other@example.com")
    other.post("/api/profile/consent", json={"agreed": True})
    base = f"/api/chat/sessions/{session_id}"
    assert other.get("/api/chat/sessions").json() == []
    assert other.get(f"{base}/messages").status_code == 404
    assert other.post(f"{base}/messages", json={"text": "hi"}).status_code == 404
    assert other.delete(base).status_code == 404
    for action in message["pending_actions"]:
        assert other.post(f"/api/chat/actions/{action['id']}/confirm").status_code == 404
        assert other.post(f"/api/chat/actions/{action['id']}/reject").status_code == 404
    rate = other.post(f"/api/chat/messages/{message['id']}/feedback", json={"rating": "up"})
    assert rate.status_code == 404
    fact = MemoryFact(user_id=chatter.get("/api/auth/me").json()["id"], text="private fact")
    db.add(fact)
    db.commit()
    assert other.get("/api/memory").json() == []
    assert other.put(f"/api/memory/{fact.id}", json={"text": "changed"}).status_code == 404
    assert other.delete(f"/api/memory/{fact.id}").status_code == 404


def test_delete_session(chatter: Api, db: Session) -> None:
    session_id = new_session(chatter)
    ask(chatter, session_id, "hello")
    assert chatter.delete(f"/api/chat/sessions/{session_id}").status_code == 204
    assert db.scalar(select(func.count()).select_from(ChatMessage)) == 0


def test_usage_page_shows_no_live_calls(chatter: Api, coordinator: Api) -> None:
    ask(chatter, new_session(chatter), "hello")
    usage = coordinator.get("/api/admin/llm-usage").json()
    assert usage["all_time"]["calls"] == 1
    assert usage["all_time"]["live_calls"] == 0
