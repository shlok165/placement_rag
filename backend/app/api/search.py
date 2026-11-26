from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, Db
from app.db.models import Application, SavedJob, SearchEvent, User
from app.schemas.search import SearchHit, SearchIn, SearchOut
from app.search.config import get_search_config
from app.search.engine import Hit, search
from app.search.nlq import parse
from app.search.profiles import load_ranking_profile

router = APIRouter(prefix="/api", tags=["search"])


def annotate(db: Db, user: User, hits: list[Hit]) -> list[SearchHit]:
    """Add the student's own saved and tracked state to each result."""
    ids = [h.job.id for h in hits]
    saved = set(
        db.scalars(
            select(SavedJob.job_id).where(SavedJob.user_id == user.id, SavedJob.job_id.in_(ids))
        )
    )
    tracked = dict(
        db.execute(
            select(Application.job_id, Application.status).where(
                Application.user_id == user.id, Application.job_id.in_(ids)
            )
        )
        .tuples()
        .all()
    )
    return [SearchHit.from_hit(h, saved, tracked) for h in hits]


class ParseIn(BaseModel):
    text: str = Field(max_length=300)


@router.post("/search/parse")
def parse_query(body: ParseIn, _: CurrentUser) -> dict[str, Any]:
    """Split a typed request into filters and a clean query. Rules only, no LLM."""
    parsed = parse(body.text)
    return {"query": parsed.query, "filters": parsed.filters, "chips": parsed.chips}


@router.post("/search", response_model=SearchOut)
def run_search(body: SearchIn, user: CurrentUser, db: Db) -> SearchOut:
    profile = load_ranking_profile(db, user.id) if body.personalize else None
    results = search(
        db,
        body.query,
        body.filters.to_filters(),
        profile=profile,
        sort=body.sort,
        limit=body.page_size,
        offset=(body.page - 1) * body.page_size,
    )
    items = annotate(db, user, results.hits)
    if body.query.strip() and body.page == 1:
        # Anonymous on purpose: the dashboard needs gaps in coverage, not who searched.
        db.add(
            SearchEvent(
                query=" ".join(body.query.split()),
                result_count=results.total,
                top_similarity=results.top_similarity,
            )
        )
        db.commit()
    return SearchOut(
        items=items,
        total=results.total,
        page=body.page,
        page_size=body.page_size,
        personalized=profile is not None and not profile.is_empty,
        weak_match=(results.top_similarity or 1.0) < get_search_config().weak_similarity,
    )
