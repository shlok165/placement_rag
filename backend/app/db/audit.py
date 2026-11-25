from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def audit(
    db: Session,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | str,
    diff: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the caller's transaction."""
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            diff=diff or {},
        )
    )
