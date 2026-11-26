"""A student's taste vector: a decayed, weighted mean of postings they acted on.

Saves, apply clicks and thumbs up pull towards a posting; a thumb down pushes away, with less
weight. Each posting counts once per kind, at its latest event. Without positive events there is
no taste vector, so a new student is ranked exactly as before.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InteractionEvent, Job
from app.search.config import TasteConfig

KINDS = ("save", "apply_clicked", "thumb_up", "thumb_down")


def combine(
    events: list[tuple[str, datetime, list[float]]], config: TasteConfig, now: datetime
) -> list[float] | None:
    """(kind, when, posting embedding) newest first -> unit taste vector, or None."""
    total: np.ndarray | None = None
    positive = 0.0
    for kind, when, embedding in events:
        vector = np.asarray(embedding, dtype=float)
        norm = float(np.linalg.norm(vector))
        if not norm:
            continue
        age_days = max(0.0, (now - when).total_seconds() / 86_400)
        weight = config.weight(kind) * 0.5 ** (age_days / config.half_life_days)
        total = vector / norm * weight if total is None else total + vector / norm * weight
        positive += max(weight, 0.0)
    if total is None or positive == 0:
        return None
    length = float(np.linalg.norm(total))
    return None if length == 0 else (total / length).tolist()


def taste_vector(
    db: Session, user_id: int, config: TasteConfig, now: datetime | None = None
) -> list[float] | None:
    if not config.enabled:
        return None
    now = now or datetime.now(UTC)
    rows = db.execute(
        select(
            InteractionEvent.job_id,
            InteractionEvent.kind,
            InteractionEvent.created_at,
            Job.embedding,
        )
        .join(Job, Job.id == InteractionEvent.job_id)
        .where(
            InteractionEvent.user_id == user_id,
            InteractionEvent.kind.in_(KINDS),
            InteractionEvent.created_at >= now - timedelta(days=config.lookback_days),
            Job.embedding.is_not(None),
        )
        .order_by(InteractionEvent.created_at.desc(), InteractionEvent.id.desc())
        .limit(config.max_events)
    ).all()
    seen: set[tuple[int, str]] = set()
    events = []
    for job_id, kind, when, embedding in rows:
        if (job_id, kind) not in seen:
            seen.add((job_id, kind))
            events.append((kind, when, list(embedding)))
    return combine(events, config, now)
