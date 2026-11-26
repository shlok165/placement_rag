"""Deadlines as a calendar: a one-off .ics download and a private feed URL that can be revoked."""

import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, Db
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.security import hash_token
from app.db.models import Application, Job, JobStatus, SavedJob, User

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

ICS = "text/calendar; charset=utf-8"
PRODUCT = "-//placement_rag//deadlines//EN"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets continue on the next line after a space (RFC 5545)."""
    out, current = [], ""
    for char in line:
        if len((current + char).encode()) > 75:
            out.append(current)
            current = " " + char
        else:
            current += char
    return [*out, current]


def deadline_jobs(db: Session, user_id: int, today: date) -> list[Job]:
    saved = select(SavedJob.job_id).where(SavedJob.user_id == user_id)
    tracked = select(Application.job_id).where(Application.user_id == user_id)
    return list(
        db.scalars(
            select(Job)
            .where(
                Job.id.in_(saved.union(tracked)),
                Job.status.in_((JobStatus.indexed, JobStatus.expired)),
                Job.deadline.is_not(None),
                Job.deadline >= today - timedelta(days=30),
            )
            .order_by(Job.deadline, Job.id)
        )
    )


def to_ics(jobs: list[Job], base_url: str, now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODUCT}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Placement deadlines",
    ]
    for job in jobs:
        assert job.deadline is not None
        start = job.deadline.strftime("%Y%m%d")
        end = (job.deadline + timedelta(days=1)).strftime("%Y%m%d")
        link = f"{base_url}/jobs/{job.id}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:job-{job.id}@placement_rag",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{start}",
            f"DTEND;VALUE=DATE:{end}",
            f"SUMMARY:{_escape(f'Apply by today: {job.title} at {job.company}')}",
            f"DESCRIPTION:{_escape(f'Last day to apply. Details: {link}')}",
            f"URL:{link}",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER:-P1D",
            f"DESCRIPTION:{_escape(f'Tomorrow is the last day for {job.title}')}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"


def _base(request: Request) -> str:
    return (get_settings().public_url or str(request.base_url)).rstrip("/")


def _calendar(db: Session, user_id: int, request: Request) -> Response:
    now = datetime.now(UTC)
    body = to_ics(deadline_jobs(db, user_id, now.date()), _base(request), now)
    return Response(body, media_type=ICS)


@router.get("/deadlines.ics")
def download(request: Request, user: CurrentUser, db: Db) -> Response:
    response = _calendar(db, user.id, request)
    response.headers["Content-Disposition"] = 'attachment; filename="placement-deadlines.ics"'
    return response


@router.get("/feed")
def feed_status(user: CurrentUser) -> dict[str, object]:
    return {"active": user.calendar_token_hash is not None, "created_at": user.calendar_created_at}


@router.post("/feed", status_code=201)
def create_feed(request: Request, user: CurrentUser, db: Db) -> dict[str, object]:
    """A new secret replaces any earlier one, so an old link stops working at once."""
    token = secrets.token_urlsafe(32)
    user.calendar_token_hash = hash_token(token)
    user.calendar_created_at = datetime.now(UTC)
    db.commit()
    return {
        "active": True,
        "created_at": user.calendar_created_at,
        # Shown once. Only its hash is stored.
        "url": f"{_base(request)}/api/calendar/feed/{token}.ics",
    }


@router.delete("/feed", status_code=204)
def revoke_feed(user: CurrentUser, db: Db) -> None:
    user.calendar_token_hash = None
    user.calendar_created_at = None
    db.commit()


@router.get("/feed/{token}.ics")
def feed(token: str, request: Request, db: Db) -> Response:
    """No session: calendar apps cannot sign in. The secret in the path is the only key."""
    user = db.scalar(
        select(User).where(User.calendar_token_hash == hash_token(token), User.is_active)
    )
    if user is None:
        raise NotFound("This calendar link is not valid. Create a new one in the portal.")
    response = _calendar(db, user.id, request)
    response.headers["Cache-Control"] = "private, max-age=900"
    return response
