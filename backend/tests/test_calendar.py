from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.api.calendar import _fold, to_ics
from app.db.models import Job, JobStatus, User
from tests.conftest import Api
from tests.test_search import TODAY, add


def test_download_lists_saved_and_tracked_deadlines_only(db: Session, student: Api) -> None:
    saved = add(db, title="Saved, Role; One", deadline=TODAY + timedelta(days=5))
    tracked = add(db, title="Tracked Role", deadline=TODAY + timedelta(days=9))
    add(db, title="Unrelated Role", deadline=TODAY + timedelta(days=3))
    student.put(f"/api/saved/{saved.id}")
    student.put(f"/api/applications/{tracked.id}", json={"status": "applied"})
    reply = student.get("/api/calendar/deadlines.ics")
    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("text/calendar")
    assert "attachment" in reply.headers["content-disposition"]
    body = reply.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert body.count("BEGIN:VEVENT") == 2
    assert f"UID:job-{saved.id}@placement_rag" in body
    assert "Saved\\, Role\\; One" in body
    assert "Unrelated" not in body
    assert f"DTSTART;VALUE=DATE:{saved.deadline:%Y%m%d}" in body


def test_hidden_postings_leave_the_calendar(db: Session, student: Api) -> None:
    job = add(db, title="Soon Gone", deadline=TODAY + timedelta(days=5))
    student.put(f"/api/saved/{job.id}")
    job.status = JobStatus.archived
    db.commit()
    assert "Soon Gone" not in student.get("/api/calendar/deadlines.ics").text


def test_feed_works_without_a_session_and_can_be_revoked(
    db: Session, student: Api, anonymous: Api
) -> None:
    job = add(db, title="Feed Role", deadline=TODAY + timedelta(days=5))
    student.put(f"/api/saved/{job.id}")
    assert student.get("/api/calendar/feed").json()["active"] is False
    created = student.post("/api/calendar/feed").json()
    path = created["url"].split("testserver", 1)[1]
    feed = anonymous.get(path)
    assert feed.status_code == 200
    assert "Feed Role" in feed.text
    assert student.get("/api/calendar/feed").json()["active"] is True
    replaced = student.post("/api/calendar/feed").json()["url"]
    assert anonymous.get(path).status_code == 404
    student.delete("/api/calendar/feed")
    assert anonymous.get(replaced.split("testserver", 1)[1]).status_code == 404


def test_feed_secret_is_long_and_stored_only_as_a_hash(db: Session, student: Api) -> None:
    url = student.post("/api/calendar/feed").json()["url"]
    token = url.rsplit("/", 1)[1].removesuffix(".ics")
    assert len(token) >= 40
    me = student.get("/api/auth/me").json()
    user = db.get(User, me["id"])
    db.refresh(user)
    assert user is not None and user.calendar_token_hash not in (None, token)


def test_guessed_feed_links_are_refused(anonymous: Api) -> None:
    assert anonymous.get("/api/calendar/feed/not-a-real-token.ics").status_code == 404


def test_long_lines_are_folded() -> None:
    job = Job(id=1, title="T" * 120, company="C", deadline=TODAY)
    body = to_ics([job], "https://example.test", datetime.now(UTC))
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert _fold("x" * 80) == ["x" * 75, " " + "x" * 5]
