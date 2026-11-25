import io
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.student import sus_score
from app.core.config import get_settings
from app.core.redaction import redact
from app.db.models import (
    Application,
    Base,
    Job,
    JobStatus,
    LlmCache,
    LlmCall,
    Notification,
    ResumeFile,
    StudentProfile,
    User,
)
from app.ingest.alerts import remind_deadlines
from app.ingest.resume_rules import parse_resume_rules
from tests.conftest import PASSWORD, Api
from tests.test_search import TODAY, add

RESUME = """Test User
Email: test.user@example.com | +91 98765 43210
linkedin.com/in/test-user-123 | github.com/testuser
Roll No: 2023CSB1099
Address: House 12, Model Town, Ropar 140001
Date of Birth: 01/02/2004
Father's Name: Someone Else

Education
B.Tech in Computer Science, IIT Ropar, 2023 - 2027
Senior Secondary, 2023

Technical Skills
Languages: Python, C++, SQL
Frameworks: React.js, FastAPI

Projects
Campus Bus Tracker
- Built a live map in React with a FastAPI backend.
- Stored trips in PostgreSQL.
Spam Filter
- Trained a classifier with scikit-learn.

Experience
Software Intern at Sample Labs, 2025
- Wrote REST APIs and cut response time by half.
"""

SECRETS = [
    "test.user@example.com",
    "98765",
    "linkedin.com/in",
    "github.com/testuser",
    "2023CSB1099",
    "Model Town",
    "01/02/2004",
    "Someone Else",
    "Test User",
]


def docx(text: str = RESUME) -> dict[str, Any]:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return {"file": ("resume.docx", buffer.getvalue(), "application/octet-stream")}


# ---------------------------------------------------------------- redaction


def test_redaction_removes_identifiers_and_keeps_skills() -> None:
    text, counts = redact(RESUME, ["Test User"])
    for secret in SECRETS:
        assert secret not in text, secret
    for kept in ("Python", "C++", "FastAPI", "Campus Bus Tracker", "2023 - 2027", "Sample Labs"):
        assert kept in text, kept
    assert counts["email"] == 1
    assert counts["phone"] == 1


@pytest.mark.parametrize(
    "value",
    [
        "me [at] mail.com",
        "a.b+c@sub.domain.ac.in",
        "+91-9876543210",
        "098765 43210",
        "(0188) 123 4567",
        "1234 5678 9012",
        "ABCDE1234F",
        "Passport: M1234567",
        "Enrollment No. 21-ME-1044",
        "https://my-site.example/resume",
    ],
)
def test_redaction_catches_variants(value: str) -> None:
    text, counts = redact(f"before {value} after")
    assert value not in text
    assert sum(counts.values()) >= 1


@pytest.mark.parametrize(
    "value", ["CGPA 8.75/10", "2021 - 2025", "Reduced cost by 35% in 2024", "Python 3.12, C++17"]
)
def test_redaction_leaves_ordinary_numbers(value: str) -> None:
    assert redact(value)[0] == value


# ---------------------------------------------------------------- resume


def test_resume_rules() -> None:
    profile = parse_resume_rules(redact(RESUME)[0])
    assert profile.education[0].degree.startswith("B.Tech in Computer Science")
    assert profile.education[0].year == "2023 - 2027"
    assert {"Python", "C++", "SQL", "React", "FastAPI", "Machine Learning"} <= set(profile.skills)
    assert [p.title for p in profile.projects] == ["Campus Bus Tracker", "Spam Filter"]
    assert "FastAPI backend" in profile.projects[0].summary
    assert profile.experience[0].role == "Software Intern"
    assert profile.experience[0].organisation.startswith("Sample Labs")


def test_upload_stores_only_redacted_text(student: Api, db: Session) -> None:
    data = student.post("/api/profile/resume", files=docx()).json()
    assert data["parsed_by"] == "local"
    assert data["redactions"]["email"] == 1
    for secret in SECRETS:
        assert secret not in data["resume_text_redacted"]
    profile = db.scalar(select(StudentProfile))
    assert profile.profile_embedding is not None
    assert "Python" in profile.skills
    assert db.scalar(select(func.count()).select_from(LlmCall)) == 0


def test_consent_lets_the_llm_client_parse(student: Api, db: Session) -> None:
    assert student.post("/api/profile/consent", json={"agreed": True}).json()["consent_at"]
    data = student.post("/api/profile/resume", files=docx()).json()
    assert data["parsed_by"] == "mock"
    call = db.scalar(select(LlmCall))
    assert (call.purpose, call.is_live) == ("parse_resume", False)
    assert student.post("/api/profile/consent", json={"agreed": False}).json()["consent_at"] is None


def test_new_resume_replaces_the_old_file(student: Api, db: Session) -> None:
    student.post("/api/profile/resume", files=docx())
    first = db.scalar(select(ResumeFile.path))
    student.post("/api/profile/resume", files=docx(RESUME + "\nGo, Rust"))
    paths = list(db.scalars(select(ResumeFile.path)))
    root = get_settings().raw_files_dir
    assert len(paths) == 1
    assert paths[0] != first
    assert not Path(root / str(first)).exists()
    student.delete("/api/profile/resume")
    assert not Path(root / paths[0]).exists()


def test_profile_edit_updates_embedding(student: Api, db: Session) -> None:
    body = {"parsed_profile": {"skills": ["k8s", "Docker"], "projects": [{"title": "X"}]}}
    data = student.put("/api/profile", json=body).json()
    assert data["skills"] == ["Kubernetes", "Docker"]
    profile = db.scalar(select(StudentProfile))
    before = list(profile.profile_embedding)
    student.put("/api/profile/preferences", json={"roles": ["Civil"], "locations": ["bangalore"]})
    db.expire_all()
    profile = db.scalar(select(StudentProfile))
    assert profile.preferences["locations"] == ["Bengaluru"]
    assert list(profile.profile_embedding) != before


def test_onboarding_flag(student: Api) -> None:
    assert student.get("/api/auth/me").json()["onboarded_at"] is None
    assert student.post("/api/profile/onboarded").json()["onboarded_at"]


# ---------------------------------------------------------------- jobs, saves, tracking


def test_job_detail_has_fit_and_similar(student: Api, db: Session) -> None:
    job = add(db, skills=["Python", "SQL"])
    other = add(db, title="Backend Intern Two")
    student.put("/api/profile", json={"parsed_profile": {"skills": ["Python"]}})
    data = student.get(f"/api/jobs/{job.id}").json()
    assert data["breakdown"]["matched_skills"] == ["Python"]
    assert data["breakdown"]["missing_skills"] == ["SQL"]
    assert [j["id"] for j in data["similar"]] == [other.id]


@pytest.mark.parametrize("status", ["draft", "pending", "failed", "archived"])
def test_hidden_jobs_look_missing(student: Api, db: Session, status: str) -> None:
    job = add(db)
    job.status = JobStatus(status)
    db.commit()
    assert student.get(f"/api/jobs/{job.id}").status_code == 404
    assert student.put(f"/api/saved/{job.id}").status_code == 404
    body = {"status": "applied"}
    assert student.put(f"/api/applications/{job.id}", json=body).status_code == 404


def test_expired_job_can_still_be_read(student: Api, db: Session) -> None:
    job = add(db)
    job.status = JobStatus.expired
    db.commit()
    assert student.get(f"/api/jobs/{job.id}").json()["job"]["status"] == "expired"


def test_save_and_unsave(student: Api, db: Session) -> None:
    job = add(db)
    assert student.put(f"/api/saved/{job.id}").status_code == 204
    assert student.put(f"/api/saved/{job.id}").status_code == 204
    assert [i["job"]["id"] for i in student.get("/api/saved").json()] == [job.id]
    student.delete(f"/api/saved/{job.id}")
    assert student.get("/api/saved").json() == []


def test_tracking_keeps_notes_when_status_changes(student: Api, db: Session) -> None:
    job = add(db)
    body = {"status": "applied", "notes": "Sent on Monday"}
    student.put(f"/api/applications/{job.id}", json=body)
    student.put(f"/api/applications/{job.id}", json={"status": "interview"})
    rows = student.get("/api/applications").json()
    assert [(r["status"], r["notes"]) for r in rows] == [("interview", "Sent on Monday")]
    bad = student.put(f"/api/applications/{job.id}", json={"status": "ghosted"})
    assert bad.status_code == 422
    student.delete(f"/api/applications/{job.id}")
    assert student.get("/api/applications").json() == []


def test_home_recommends_by_profile_and_skips_tracked(student: Api, db: Session) -> None:
    fit = add(db, title="Data Analyst Intern", skills=["SQL"], location="Delhi")
    add(db, title="Welder", skills=["Manufacturing"], location="Chennai")
    student.put("/api/profile", json={"parsed_profile": {"skills": ["SQL"]}})
    student.put("/api/profile/preferences", json={"roles": ["Data Analytics"]})
    data = student.get("/api/home").json()
    assert data["recommended"][0]["job"]["id"] == fit.id
    assert data["profile_ready"] is True
    student.put(f"/api/applications/{fit.id}", json={"status": "applied"})
    data = student.get("/api/home").json()
    assert fit.id not in [i["job"]["id"] for i in data["recommended"]]
    assert data["pipeline"] == {"applied": 1}


def test_home_works_with_an_empty_profile(student: Api, db: Session) -> None:
    add(db)
    data = student.get("/api/home").json()
    assert data["profile_ready"] is False
    assert len(data["recommended"]) == 1


def test_deadline_reminders_once_and_not_after_applying(student: Api, db: Session) -> None:
    soon = add(db, title="Closing", deadline=TODAY + timedelta(days=2))
    done = add(db, title="Done", deadline=TODAY + timedelta(days=2))
    student.put(f"/api/saved/{soon.id}")
    student.put(f"/api/saved/{done.id}")
    student.put(f"/api/applications/{done.id}", json={"status": "applied"})
    assert remind_deadlines(db) == 1
    db.commit()
    assert remind_deadlines(db) == 0
    items = student.get("/api/notifications").json()
    assert [n["payload"]["job_id"] for n in items] == [soon.id]
    assert student.get("/api/notifications/unread").json() == {"unread": 1}
    student.post("/api/notifications/read")
    assert student.get("/api/notifications/unread").json() == {"unread": 0}


def test_saved_searches(student: Api) -> None:
    body = {"name": "Remote ML", "query": "ml", "filters": {"remote": True}}
    created = student.post("/api/saved-searches", json=body).json()
    assert student.get("/api/saved-searches").json() == [created]
    student.delete(f"/api/saved-searches/{created['id']}")
    assert student.get("/api/saved-searches").json() == []


def test_announcement_reaches_students(student: Api, coordinator: Api) -> None:
    assert student.get("/api/announcement").json()["message"] is None
    coordinator.post("/api/admin/announcements", json={"message": "Mock interviews on Friday"})
    assert student.get("/api/announcement").json()["message"] == "Mock interviews on Friday"


def test_sus_score() -> None:
    assert sus_score([5, 1] * 5) == 100.0
    assert sus_score([3] * 10) == 50.0
    assert sus_score([1, 5] * 5) == 0.0


def test_feedback_and_sus_reach_coordinators(student: Api, coordinator: Api) -> None:
    student.post("/api/feedback", json={"message": "Love the filters", "category": "praise"})
    student.post("/api/sus", json={"answers": [4, 2] * 5})
    student.post("/api/sus", json={"answers": [5, 1] * 5})
    data = coordinator.get("/api/admin/feedback").json()
    assert data["items"][0]["message"] == "Love the filters"
    assert data["sus"] == {"responses": 1, "mean": 100.0}
    assert "email" not in str(data)


# ---------------------------------------------------------------- isolation and deletion


def test_students_never_see_each_other(login: Any, db: Session) -> None:
    first, second = login("a@example.com"), login("b@example.com")
    job = add(db)
    first.put(f"/api/saved/{job.id}")
    first.put(f"/api/applications/{job.id}", json={"status": "offer", "notes": "private"})
    search_id = first.post("/api/saved-searches", json={"name": "mine"}).json()["id"]
    first.put("/api/profile", json={"parsed_profile": {"skills": ["Haskell"]}})
    owner = db.scalar(select(User.id).where(User.email == "a@example.com"))
    db.add(Notification(user_id=owner, type="new_match", payload={}))
    db.commit()
    notification = db.scalar(select(Notification.id))

    assert second.get("/api/saved").json() == []
    assert second.get("/api/applications").json() == []
    assert second.get("/api/saved-searches").json() == []
    assert second.get("/api/notifications").json() == []
    assert second.get("/api/profile").json()["skills"] == []
    assert "private" not in second.get("/api/profile/export").text
    assert second.get("/api/home").json()["pipeline"] == {}
    detail = second.get(f"/api/jobs/{job.id}").json()
    assert (detail["saved"], detail["application"]) == (False, None)

    second.delete(f"/api/applications/{job.id}")
    second.delete(f"/api/saved/{job.id}")
    second.delete(f"/api/saved-searches/{search_id}")
    second.post(f"/api/notifications/{notification}/read")
    assert len(first.get("/api/applications").json()) == 1
    assert len(first.get("/api/saved").json()) == 1
    assert len(first.get("/api/saved-searches").json()) == 1
    assert first.get("/api/notifications/unread").json() == {"unread": 1}


def test_export_contains_everything_owned(student: Api, db: Session) -> None:
    job = add(db)
    student.post("/api/profile/resume", files=docx())
    student.put(f"/api/applications/{job.id}", json={"status": "applied"})
    response = student.get("/api/profile/export")
    data = response.json()
    assert "attachment" in response.headers["Content-Disposition"]
    assert data["applications"][0]["status"] == "applied"
    assert "Python" in data["profile"]["skills"]
    assert "password" not in response.text


def test_delete_account_removes_all_personal_rows(student: Api, db: Session) -> None:
    job = add(db)
    student.post("/api/profile/resume", files=docx())
    student.put(f"/api/saved/{job.id}")
    student.put(f"/api/applications/{job.id}", json={"status": "applied"})
    student.post("/api/feedback", json={"message": "hello there"})
    user_id = student.get("/api/auth/me").json()["id"]
    db.add(LlmCache(prompt_hash="h", model="m", user_id=user_id, response={}))
    db.add(Notification(user_id=user_id, type="new_match", payload={}))
    db.commit()
    path = get_settings().raw_files_dir / str(db.scalar(select(ResumeFile.path)))
    assert path.exists()

    wrong = student.post("/api/profile/delete-account", json={"password": "nope"})
    assert wrong.status_code == 400
    assert (
        student.post("/api/profile/delete-account", json={"password": PASSWORD}).status_code == 204
    )
    assert student.get("/api/auth/me").status_code == 401
    assert not path.exists()
    db.expire_all()
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.columns:
            column = table.c.user_id
            left = db.scalar(select(func.count()).select_from(table).where(column == user_id))
            assert left == 0, table.name
    assert db.scalar(select(func.count()).select_from(Application)) == 0
    assert db.get(Job, job.id) is not None


def test_last_coordinator_cannot_delete_the_account(coordinator: Api) -> None:
    response = coordinator.post("/api/profile/delete-account", json={"password": PASSWORD})
    assert response.status_code == 409
