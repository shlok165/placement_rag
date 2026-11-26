"""The signed-in student's profile, preferences, consent and account."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, Db
from app.core.errors import AppError, Conflict
from app.core.security import clear_cookies, verify_password
from app.core.storage import get_storage
from app.core.uploads import extract_text, read_document
from app.db.audit import audit
from app.db.models import (
    Application,
    ChatMessage,
    ChatSession,
    InteractionEvent,
    Job,
    MemoryFact,
    Notification,
    ResumeFile,
    Role,
    SavedJob,
    SavedSearch,
    StudentProfile,
    User,
)
from app.ingest.duplicates import hash_bytes
from app.ingest.resume import parse_resume
from app.llm.client import get_llm
from app.schemas.auth import UserOut
from app.schemas.student import (
    ParsedProfile,
    PreferencesIn,
    ProfileIn,
    ProfileOut,
    ResumeOut,
)
from app.search.profiles import refresh_embedding

router = APIRouter(prefix="/api/profile", tags=["profile"])


def get_profile(db: Db, user: User) -> StudentProfile:
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def _out(db: Db, profile: StudentProfile) -> dict[str, Any]:
    name = None
    if profile.resume_file_id:
        name = db.scalar(
            select(ResumeFile.original_name).where(ResumeFile.id == profile.resume_file_id)
        )
    parsed = ParsedProfile.model_validate(profile.parsed_profile or {})
    parsed.skills = list(profile.skills or [])
    return {
        "skills": profile.skills or [],
        "parsed_profile": parsed,
        "preferences": PreferencesIn.model_validate(profile.preferences or {}),
        "resume_name": name,
        "resume_text_redacted": profile.resume_text_redacted,
        "updated_at": profile.updated_at,
    }


def _store(profile: StudentProfile, parsed: ParsedProfile) -> None:
    profile.skills = parsed.skills
    profile.parsed_profile = parsed.model_dump(exclude={"skills"})
    refresh_embedding(profile)


def _delete_resume(db: Db, user: User, keep_id: int | None = None) -> list[str]:
    """Remove stored resume rows and return the file keys to delete after commit."""
    rows = db.scalars(select(ResumeFile).where(ResumeFile.user_id == user.id)).all()
    old = [r for r in rows if r.id != keep_id]
    for row in old:
        db.delete(row)
    return [r.path for r in old]


@router.get("", response_model=ProfileOut)
def read(user: CurrentUser, db: Db) -> dict[str, Any]:
    profile = get_profile(db, user)
    db.commit()
    return _out(db, profile)


@router.put("", response_model=ProfileOut)
def update(body: ProfileIn, user: CurrentUser, db: Db) -> dict[str, Any]:
    profile = get_profile(db, user)
    _store(profile, body.parsed_profile)
    db.commit()
    return _out(db, profile)


@router.put("/preferences", response_model=ProfileOut)
def update_preferences(body: PreferencesIn, user: CurrentUser, db: Db) -> dict[str, Any]:
    profile = get_profile(db, user)
    profile.preferences = body.model_dump()
    refresh_embedding(profile)
    db.commit()
    return _out(db, profile)


@router.post("/resume", response_model=ResumeOut)
def upload_resume(user: CurrentUser, db: Db, file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    upload = read_document(file)
    text = extract_text(upload.data, upload.mime)
    parsed, redacted, counts, parsed_by = parse_resume(
        get_llm(), text, user.full_name, user.id, may_use_llm=user.consent_at is not None
    )
    profile = get_profile(db, user)
    row = ResumeFile(
        user_id=user.id,
        path=get_storage().save("resumes", upload.data, upload.extension),
        original_name=upload.name,
        mime=upload.mime,
        sha256=hash_bytes(upload.data),
    )
    db.add(row)
    db.flush()
    profile.resume_file_id = row.id
    profile.resume_text_redacted = redacted
    _store(profile, parsed)
    stale = _delete_resume(db, user, keep_id=row.id)
    db.commit()
    for path in stale:
        get_storage().delete(path)
    return {**_out(db, profile), "redactions": counts, "parsed_by": parsed_by}


@router.delete("/resume", response_model=ProfileOut)
def remove_resume(user: CurrentUser, db: Db) -> dict[str, Any]:
    profile = get_profile(db, user)
    profile.resume_file_id = None
    profile.resume_text_redacted = None
    paths = _delete_resume(db, user)
    db.commit()
    for path in paths:
        get_storage().delete(path)
    return _out(db, profile)


@router.post("/onboarded", response_model=UserOut)
def finish_onboarding(user: CurrentUser, db: Db) -> User:
    user.onboarded_at = user.onboarded_at or datetime.now(UTC)
    db.commit()
    return user


class ConsentIn(BaseModel):
    agreed: bool


@router.post("/consent", response_model=UserOut)
def set_consent(body: ConsentIn, user: CurrentUser, db: Db) -> User:
    """Agreement to send redacted text to the LLM provider. Can be withdrawn at any time."""
    user.consent_at = datetime.now(UTC) if body.agreed else None
    db.commit()
    return user


@router.get("/export")
def export(user: CurrentUser, db: Db, response: Response) -> dict[str, Any]:
    profile = get_profile(db, user)
    db.commit()
    applications = db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id)
    )
    saved = db.execute(
        select(Job.id, Job.title, Job.company, SavedJob.created_at)
        .join(SavedJob, SavedJob.job_id == Job.id)
        .where(SavedJob.user_id == user.id)
    )
    sessions = db.scalars(select(ChatSession).where(ChatSession.user_id == user.id))
    response.headers["Content-Disposition"] = 'attachment; filename="placement_rag-my-data.json"'
    return {
        "account": UserOut.model_validate(user),
        "profile": _out(db, profile),
        "applications": [
            {
                "job": {"id": j.id, "title": j.title, "company": j.company},
                "status": a.status,
                "notes": a.notes,
                "updated_at": a.updated_at,
            }
            for a, j in applications
        ],
        "saved_jobs": [
            {"id": i, "title": t, "company": c, "saved_at": at} for i, t, c, at in saved
        ],
        "saved_searches": [
            {"name": s.name, "query": s.query, "filters": s.filters}
            for s in db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id))
        ],
        "memory": [
            {"text": m.text, "kind": m.kind, "created_at": m.created_at}
            for m in db.scalars(select(MemoryFact).where(MemoryFact.user_id == user.id))
        ],
        "activity": [
            {"job_id": e.job_id, "kind": e.kind, "at": e.created_at}
            for e in db.scalars(
                select(InteractionEvent)
                .where(InteractionEvent.user_id == user.id)
                .order_by(InteractionEvent.id)
            )
        ],
        "notifications": [
            {"type": n.type, "payload": n.payload, "created_at": n.created_at}
            for n in db.scalars(select(Notification).where(Notification.user_id == user.id))
        ],
        "conversations": [
            {
                "title": s.title,
                "messages": [
                    {"role": m.role, "content": m.content, "created_at": m.created_at}
                    for m in db.scalars(
                        select(ChatMessage)
                        .where(ChatMessage.session_id == s.id)
                        .order_by(ChatMessage.id)
                    )
                ],
            }
            for s in sessions
        ],
    }


class DeleteIn(BaseModel):
    password: str


@router.post("/delete-account", status_code=204)
def delete_account(body: DeleteIn, user: CurrentUser, db: Db, response: Response) -> None:
    """Remove the account and everything linked to it, including stored files."""
    if not verify_password(user.password_hash, body.password):
        raise AppError("That password is not correct.", code="bad_password")
    if user.role == Role.coordinator:
        others = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.coordinator, User.is_active, User.id != user.id)
        )
        if not others:
            raise Conflict("You are the only coordinator. Invite another one first.")
    paths = list(db.scalars(select(ResumeFile.path).where(ResumeFile.user_id == user.id)))
    audit(db, None, "account_deleted", "user", user.id)
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    for path in paths:
        get_storage().delete(path)
    clear_cookies(response)
