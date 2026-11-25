import io
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from docx import Document
from reportlab.pdfgen import canvas
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db.models import AuditLog, IngestTask, Job, Notification, StudentProfile, User
from app.embeddings import embed_passages
from app.ingest import tasks
from app.ingest.duplicates import find_similar
from app.ingest.rules import parse_date, parse_duration, parse_pay, parse_posting
from tests.conftest import Api

SOON = (datetime.now(UTC) + timedelta(days=20)).date()

POSTING = f"""Company: Northwind Analytics
Role: Data Science Intern
Location: Pune (hybrid)
Duration: 6 months
Stipend: ₹40,000 - 55,000 per month
Deadline: {SOON.strftime("%d %B %Y")}
Skills: Python, sklearn, Pandas, SQL
Apply: https://careers.example.com/ds-intern

About the role:
Build forecasting models with the demand team and ship them to production dashboards.
"""

FORM: dict[str, Any] = {
    "company": "Acme Systems",
    "title": "Backend Engineering Intern",
    "description": "Build and operate APIs for the billing platform.",
    "skills": ["Python", "postgres"],
    "location": "bangalore",
    "job_type": "internship",
    "deadline": SOON.isoformat(),
}


def run_worker(db: Session) -> int:
    count = 0
    while tasks.process_one(db):
        count += 1
    db.expire_all()
    return count


def searchable(db: Session, job_id: int) -> bool:
    row = db.execute(
        text("SELECT embedding IS NOT NULL AND tsv IS NOT NULL FROM jobs WHERE id = :id"),
        {"id": job_id},
    ).scalar()
    return bool(row)


# ---------------------------------------------------------------- rules parser


def test_rules_parser_reads_labelled_posting() -> None:
    job = parse_posting(POSTING)
    assert job.company == "Northwind Analytics"
    assert job.title == "Data Science Intern"
    assert job.location == "Pune"
    assert job.skills == ["Python", "Machine Learning", "Pandas", "SQL"]
    assert (job.stipend_min, job.stipend_max) == (40_000, 55_000)
    assert job.duration_months == 6
    assert job.deadline == SOON
    assert job.apply_url == "https://careers.example.com/ds-intern"
    assert job.confidence["company"] == "high"


def test_rules_parser_reads_prose() -> None:
    job = parse_posting(
        "Zephyr Labs is hiring a Firmware Engineer in Hyderabad. You will write embedded C for "
        "STM32 boards and debug RTOS tasks. CTC 14 - 18 LPA. Apply before Jan 5, 2031."
    )
    assert job.company == "Zephyr Labs"
    assert job.title == "Firmware Engineer"
    assert job.location == "Hyderabad"
    assert job.job_type == "full-time"
    assert (job.stipend_min, job.stipend_max) == (1_400_000, 1_800_000)
    assert job.deadline == date(2031, 1, 5)
    assert "Embedded Systems" in job.skills


def test_rules_parser_does_not_read_remote_sensing_as_remote_work() -> None:
    job = parse_posting("Kiteway is hiring a Remote Sensing Intern in Delhi. Map crop health.")
    assert (job.title, job.remote) == ("Remote Sensing Intern", False)
    assert parse_posting("Kiteway is hiring a Data Intern. Remote work is fine.").remote is True


def test_rules_parser_marks_missing_fields_low() -> None:
    job = parse_posting("We have an exciting opportunity. Write to us for more details please.")
    assert job.confidence["company"] == "low"
    assert job.confidence["deadline"] == "low"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2031-02-03", date(2031, 2, 3)),
        ("03/02/2031", date(2031, 2, 3)),
        ("3rd Feb 2031", date(2031, 2, 3)),
        ("Feb 3, 2031", date(2031, 2, 3)),
        ("31 February 2031", None),
        ("soon", None),
    ],
)
def test_parse_date(value: str, expected: date | None) -> None:
    assert parse_date(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("40k-60k", (40_000, 60_000)),
        ("INR 25,000 per month", (25_000, 25_000)),
        ("12 LPA", (1_200_000, 1_200_000)),
        ("1.2 - 1.8 lakh", (120_000, 180_000)),
        ("unpaid", (None, None)),
    ],
)
def test_parse_pay(value: str, expected: tuple[int | None, int | None]) -> None:
    assert parse_pay(value) == expected


def test_parse_duration() -> None:
    assert parse_duration("8 weeks") == 2
    assert parse_duration("2-3 months") == 2
    assert parse_duration("flexible") is None


# ---------------------------------------------------------------- intake


def test_form_publish_reaches_indexed(coordinator: Api, db: Session) -> None:
    created = coordinator.post("/api/admin/jobs", json=FORM).json()
    assert created["status"] == "pending"
    assert run_worker(db) == 1
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["status"] == "indexed"
    assert detail["indexed"] is True
    assert detail["location"] == "Bengaluru"
    assert detail["skills"] == ["Python", "SQL"]
    assert searchable(db, created["id"])


def test_form_draft_is_not_searchable(coordinator: Api, db: Session) -> None:
    created = coordinator.post("/api/admin/jobs", json={**FORM, "action": "draft"}).json()
    assert created["status"] == "draft"
    assert run_worker(db) == 0
    assert not searchable(db, created["id"])


def test_publish_requires_core_fields(coordinator: Api) -> None:
    response = coordinator.post("/api/admin/jobs", json={**FORM, "company": " "})
    assert response.json()["error"]["code"] == "not_publishable"
    assert response.json()["error"]["details"][0]["field"] == "company"


def test_publish_rejects_past_deadline(coordinator: Api) -> None:
    response = coordinator.post("/api/admin/jobs", json={**FORM, "deadline": "2020-01-01"})
    assert response.json()["error"]["details"][0]["field"] == "deadline"


def test_invalid_link_and_stipend_are_rejected(coordinator: Api) -> None:
    bad_link = coordinator.post("/api/admin/jobs", json={**FORM, "apply_url": "javascript:x"})
    assert bad_link.status_code == 422
    body = {**FORM, "stipend_min": 50, "stipend_max": 10}
    assert coordinator.post("/api/admin/jobs", json=body).status_code == 422


def test_paste_is_parsed_then_reviewed_then_published(coordinator: Api, db: Session) -> None:
    created = coordinator.post("/api/admin/jobs/paste", json={"text": POSTING}).json()
    run_worker(db)
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["status"] == "draft"
    assert detail["parse_meta"]["needs_review"] is True
    assert detail["raw_text"] == POSTING
    assert detail["company"] == "Northwind Analytics"
    coordinator.post(f"/api/admin/jobs/{created['id']}/publish")
    run_worker(db)
    assert coordinator.get(f"/api/admin/jobs/{created['id']}").json()["status"] == "indexed"


def test_auto_publish_skips_review(coordinator: Api, db: Session) -> None:
    body = {"text": POSTING, "auto_publish": True}
    created = coordinator.post("/api/admin/jobs/paste", json=body).json()
    run_worker(db)
    assert coordinator.get(f"/api/admin/jobs/{created['id']}").json()["status"] == "indexed"


def test_auto_publish_waits_for_review_when_company_is_missing(
    coordinator: Api, db: Session
) -> None:
    body = {
        "text": "An opportunity to work on something interesting, more soon.",
        "auto_publish": True,
    }
    created = coordinator.post("/api/admin/jobs/paste", json=body).json()
    run_worker(db)
    assert coordinator.get(f"/api/admin/jobs/{created['id']}").json()["status"] == "draft"


def _docx(content: str) -> bytes:
    document = Document()
    for line in content.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf(content: str) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(content.replace("₹", "INR ").splitlines()):
        page.drawString(40, 800 - 18 * index, line)
    page.save()
    return buffer.getvalue()


@pytest.mark.parametrize("build", [_docx, _pdf])
def test_upload_is_extracted_and_parsed(coordinator: Api, db: Session, build: Any) -> None:
    files = {"file": ("posting.bin", build(POSTING), "application/octet-stream")}
    created = coordinator.post("/api/admin/jobs/upload", files=files).json()
    run_worker(db)
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["company"] == "Northwind Analytics"
    assert detail["file_name"] == "posting.bin"
    assert coordinator.get(f"/api/admin/jobs/{created['id']}/file").status_code == 200


def test_upload_rejects_other_types_whatever_the_name(coordinator: Api) -> None:
    files = {"file": ("posting.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")}
    response = coordinator.post("/api/admin/jobs/upload", files=files)
    assert response.json()["error"]["code"] == "file_type"


def test_upload_rejects_large_files(coordinator: Api) -> None:
    files = {"file": ("big.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024 + 1), "application/pdf")}
    assert coordinator.post("/api/admin/jobs/upload", files=files).status_code == 413


def test_upload_name_cannot_escape_storage(coordinator: Api, db: Session) -> None:
    files = {"file": ("../../etc/passwd.pdf", _pdf(POSTING), "application/pdf")}
    created = coordinator.post("/api/admin/jobs/upload", files=files).json()
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["file_name"] == "passwd.pdf"


def test_unreadable_file_fails_visibly_and_can_be_retried(coordinator: Api, db: Session) -> None:
    files = {"file": ("scan.pdf", b"%PDF-1.4 broken", "application/pdf")}
    created = coordinator.post("/api/admin/jobs/upload", files=files).json()
    run_worker(db)
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["status"] == "failed"
    assert "could not be read" in detail["last_error"]
    retried = coordinator.post(f"/api/admin/jobs/{created['id']}/retry").json()
    assert retried["status"] == "pending"


def test_transient_failure_is_retried_then_reported(
    coordinator: Api, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = coordinator.post("/api/admin/jobs", json=FORM).json()

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(tasks, "index_job", broken)
    for attempt in range(1, 4):
        assert tasks.process_one(db)
        db.expire_all()
        task = db.scalar(select(IngestTask).where(IngestTask.job_id == created["id"]))
        assert task is not None
        assert task.attempts == attempt
        db.execute(update(IngestTask).values(run_after=datetime.now(UTC) - timedelta(minutes=1)))
        db.commit()
    detail = coordinator.get(f"/api/admin/jobs/{created['id']}").json()
    assert detail["status"] == "failed"
    assert "secret" not in detail["last_error"]
    monkeypatch.undo()
    coordinator.post(f"/api/admin/jobs/{created['id']}/retry")
    run_worker(db)
    assert coordinator.get(f"/api/admin/jobs/{created['id']}").json()["status"] == "indexed"


def test_abandoned_task_is_picked_up_again(coordinator: Api, db: Session) -> None:
    coordinator.post("/api/admin/jobs", json=FORM)
    old = datetime.now(UTC) - timedelta(minutes=30)
    db.execute(update(IngestTask).values(status="running", locked_at=old))
    db.commit()
    assert run_worker(db) == 1


CSV = (
    "company,title,description,skills,location,remote,job_type,deadline,stipend_min\n"
    f'Orbit,QA Intern,Test the app,"Testing, Python",Delhi,no,internship,{SOON},"20,000"\n'
    f"Orbit,QA Intern,Test the app,Testing,Delhi,no,internship,{SOON},20000\n"
    f",Broken row,No company,,,,internship,{SOON},\n"
    "Orbit,Bad date,Text,,,,internship,not-a-date,\n"
)


def test_csv_import_reports_every_row(coordinator: Api, db: Session) -> None:
    files = {"file": ("jobs.csv", CSV.encode(), "text/csv")}
    response = coordinator.post("/api/admin/jobs/csv", files=files, data={"publish": "true"})
    result = response.json()
    assert (result["created"], result["duplicates"], result["invalid"]) == (1, 1, 2)
    assert [r["row"] for r in result["rows"]] == [2, 3, 4, 5]
    assert run_worker(db) == 1


def test_csv_needs_header(coordinator: Api) -> None:
    files = {"file": ("jobs.csv", b"a,b\n1,2\n", "text/csv")}
    response = coordinator.post("/api/admin/jobs/csv", files=files)
    assert response.json()["error"]["code"] == "csv_header"


# ---------------------------------------------------------------- duplicates


def test_exact_duplicate_is_refused(coordinator: Api) -> None:
    first = coordinator.post("/api/admin/jobs", json=FORM).json()
    again = coordinator.post("/api/admin/jobs", json=FORM)
    assert again.status_code == 409
    assert again.json()["error"]["details"]["job_id"] == first["id"]


def test_near_duplicate_is_flagged(coordinator: Api, db: Session) -> None:
    first = coordinator.post("/api/admin/jobs", json=FORM).json()
    body = {
        **FORM,
        "company": "Acme Systems Pvt. Ltd.",
        "title": "Intern, Backend Engineering",
        "deadline": (SOON + timedelta(days=1)).isoformat(),
        "description": "Something else entirely.",
    }
    second = coordinator.post("/api/admin/jobs", json=body).json()
    assert second["duplicate_of_id"] == first["id"]
    assert second["duplicates"][0]["id"] == first["id"]


def test_different_role_or_date_is_not_a_duplicate(coordinator: Api, db: Session) -> None:
    coordinator.post("/api/admin/jobs", json=FORM)
    assert find_similar(db, "Acme Systems", "Marketing Intern", SOON) == []
    assert find_similar(db, FORM["company"], FORM["title"], SOON + timedelta(days=30)) == []


def test_auto_publish_holds_likely_duplicates(coordinator: Api, db: Session) -> None:
    coordinator.post("/api/admin/jobs/paste", json={"text": POSTING, "auto_publish": True})
    run_worker(db)
    changed = POSTING + "\nFood and travel are covered."
    second = coordinator.post(
        "/api/admin/jobs/paste", json={"text": changed, "auto_publish": True}
    ).json()
    run_worker(db)
    detail = coordinator.get(f"/api/admin/jobs/{second['id']}").json()
    assert detail["status"] == "draft"
    assert detail["duplicate_of_id"] is not None


# ---------------------------------------------------------------- edit and lifecycle


@pytest.fixture
def live_job(coordinator: Api, db: Session) -> int:
    created = coordinator.post("/api/admin/jobs", json=FORM).json()
    run_worker(db)
    return int(created["id"])


def test_edit_reindexes_in_the_same_transaction(
    coordinator: Api, db: Session, live_job: int
) -> None:
    before = list(db.get(Job, live_job).embedding)
    response = coordinator.patch(
        f"/api/admin/jobs/{live_job}",
        json={"title": "Marine Biology Intern", "description": "Study coral reefs."},
    )
    assert response.json()["status"] == "indexed"
    db.expire_all()
    job = db.get(Job, live_job)
    assert list(job.embedding) != before
    assert "coral" in str(job.tsv)
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "edited"))
    assert entry.diff["title"]["to"] == "Marine Biology Intern"


def test_failed_reindex_rolls_back_the_edit(
    coordinator: Api, db: Session, live_job: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_: object) -> None:
        raise RuntimeError

    monkeypatch.setattr("app.ingest.service.index_job", broken)
    with pytest.raises(RuntimeError):
        coordinator.patch(f"/api/admin/jobs/{live_job}", json={"title": "Changed title"})
    db.expire_all()
    assert db.get(Job, live_job).title == FORM["title"]


def test_archive_and_undo(coordinator: Api, live_job: int) -> None:
    assert coordinator.post(f"/api/admin/jobs/{live_job}/archive").json()["status"] == "archived"
    assert coordinator.post(f"/api/admin/jobs/{live_job}/restore").json()["status"] == "indexed"


def test_manual_expire_and_undo(coordinator: Api, live_job: int) -> None:
    assert coordinator.post(f"/api/admin/jobs/{live_job}/expire").json()["status"] == "expired"
    assert coordinator.post(f"/api/admin/jobs/{live_job}/restore").json()["status"] == "indexed"


def test_nightly_expiry(coordinator: Api, db: Session, live_job: int) -> None:
    db.execute(update(Job).values(deadline=datetime.now(UTC).date() - timedelta(days=1)))
    db.commit()
    evening = datetime.now(UTC).replace(hour=20)
    assert tasks.schedule_nightly(db, evening) is True
    assert tasks.schedule_nightly(db, evening) is False
    run_worker(db)
    assert coordinator.get(f"/api/admin/jobs/{live_job}").json()["status"] == "expired"
    blocked = coordinator.post(f"/api/admin/jobs/{live_job}/restore")
    assert blocked.json()["error"]["code"] == "deadline_passed"
    reopened = coordinator.patch(f"/api/admin/jobs/{live_job}", json={"deadline": SOON.isoformat()})
    assert reopened.json()["status"] == "indexed"


def test_schedule_waits_for_the_hour(db: Session) -> None:
    assert tasks.schedule_nightly(db, datetime(2031, 1, 1, 3, tzinfo=UTC)) is False


def test_delete_needs_archive_first(coordinator: Api, db: Session, live_job: int) -> None:
    assert coordinator.delete(f"/api/admin/jobs/{live_job}").status_code == 409
    coordinator.post(f"/api/admin/jobs/{live_job}/archive")
    assert coordinator.delete(f"/api/admin/jobs/{live_job}").status_code == 204
    assert db.get(Job, live_job) is None


def test_bulk_archive(coordinator: Api, live_job: int) -> None:
    body = {"ids": [live_job, 9999], "action": "archive"}
    assert coordinator.post("/api/admin/jobs/bulk", json=body).json() == {"done": 1, "skipped": 1}


def test_list_filters_sorts_and_pages(coordinator: Api, db: Session) -> None:
    for index in range(3):
        coordinator.post("/api/admin/jobs", json={**FORM, "title": f"Role number {index}"})
    run_worker(db)
    page = coordinator.get("/api/admin/jobs?page_size=2&sort=title&q=role").json()
    assert page["total"] == 3
    assert [i["title"] for i in page["items"]] == ["Role number 0", "Role number 1"]
    assert coordinator.get("/api/admin/jobs?status=draft").json()["total"] == 0
    late = (SOON + timedelta(days=1)).isoformat()
    assert coordinator.get(f"/api/admin/jobs?deadline_from={late}").json()["total"] == 0


def test_history_lists_changes(coordinator: Api, live_job: int) -> None:
    coordinator.patch(f"/api/admin/jobs/{live_job}", json={"location": "Pune"})
    actions = [h["action"] for h in coordinator.get(f"/api/admin/jobs/{live_job}/history").json()]
    assert actions == ["edited", "published", "created"]


# ---------------------------------------------------------------- alerts


def _profile(
    db: Session, email: str, text_: str, preferences: dict[str, Any], make_user: Any
) -> User:
    user = make_user(email)
    profile = db.get(StudentProfile, user.id)
    profile.preferences = preferences
    profile.profile_embedding = embed_passages([text_])[0]
    db.commit()
    return user


def test_alerts_respect_similarity_and_hard_filters(
    coordinator: Api, db: Session, make_user: Any
) -> None:
    fit = "Backend Engineering Intern. Python and SQL developer who builds APIs."
    match = _profile(db, "m@example.com", fit, {"locations": ["Bengaluru"]}, make_user)
    _profile(db, "l@example.com", fit, {"locations": ["Delhi"]}, make_user)
    _profile(db, "t@example.com", fit, {"job_types": ["full-time"]}, make_user)
    _profile(db, "f@example.com", "Oil painting and renaissance poetry", {}, make_user)
    coordinator.post("/api/admin/jobs", json=FORM)
    run_worker(db)
    notified = list(db.scalars(select(Notification.user_id)))
    assert notified == [match.id]


def test_reindex_does_not_alert_again(
    coordinator: Api, db: Session, make_user: Any, live_job: int
) -> None:
    _profile(db, "m@example.com", "Backend Engineering Intern Python APIs", {}, make_user)
    coordinator.post(f"/api/admin/jobs/{live_job}/reindex")
    run_worker(db)
    assert list(db.scalars(select(Notification.id))) == []


# ---------------------------------------------------------------- insights


def test_dashboard_and_usage(coordinator: Api, live_job: int) -> None:
    data = coordinator.get("/api/admin/dashboard").json()
    assert data["postings_by_status"]["indexed"] == 1
    usage = coordinator.get("/api/admin/llm-usage").json()
    assert usage["mode"] == "mock"
    assert usage["budget"]["live_total"] == 0


def test_student_lookup_is_audited(coordinator: Api, make_user: Any, db: Session) -> None:
    make_user("s@example.com")
    assert coordinator.get("/api/admin/students").json()["total"] == 1
    body = {"email": "s@example.com", "reason": "Verifying an offer letter"}
    assert coordinator.post("/api/admin/students/lookup", json=body).status_code == 200
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "student_viewed"))
    assert entry.diff["reason"] == body["reason"]
