from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.metrics import metrics
from app.db.models import IngestTask, LlmCall
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1 FROM alembic_version"))
    except Exception:
        response.status_code = 503
        return {"status": "database not ready"}
    return {"status": "ready"}


@router.get("/metrics")
def prometheus(db: Annotated[Session, Depends(get_db)]) -> Response:
    queued = (IngestTask.status == "queued") | (IngestTask.status == "running")
    gauges = {
        "ingest_queue_depth": float(
            db.scalar(select(func.count()).select_from(IngestTask).where(queued)) or 0
        ),
        "llm_calls_total": float(db.scalar(select(func.count()).select_from(LlmCall)) or 0),
        "llm_live_calls_total": float(
            db.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.is_live)) or 0
        ),
    }
    return Response(metrics.render(gauges), media_type="text/plain; version=0.0.4")
