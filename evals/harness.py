"""Runs retrieval cases against a database and scores them."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.embeddings import embed_passages
from app.search.config import SearchConfig, get_search_config
from app.search.engine import Mode, search
from app.search.matching import Preferences
from app.search.profiles import profile_passage
from app.search.ranking import Profile
from evals.metrics import hit_at, mean, ndcg_at, recall_at, reciprocal_rank
from evals.stats import interval, paired_difference

INTERVAL_METRICS = ("hit@1", "hit@5", "mrr", "ndcg@10")


@dataclass
class RunConfig:
    name: str
    mode: Mode = "hybrid"
    personalize: bool = False
    overrides: dict[str, Any] | None = None

    def search_config(self) -> SearchConfig:
        return get_search_config().override(self.overrides or {})


@dataclass
class LabelledCase:
    query: str
    profile: dict[str, Any]
    relevant: set[int]
    slice: str = "all"


STANDARD_CONFIGS = [
    RunConfig("Semantic only", mode="semantic"),
    RunConfig("Keyword only", mode="keyword"),
    RunConfig("Hybrid"),
    RunConfig("Hybrid + personal re-rank", personalize=True),
]


def make_profile(snapshot: dict[str, Any], cache: dict[str, Profile]) -> Profile:
    key = repr(sorted(snapshot.items(), key=lambda kv: kv[0]))
    if key not in cache:
        skills = list(snapshot.get("skills") or [])
        preferences = dict(snapshot.get("preferences") or {})
        passage = profile_passage(skills, preferences)
        vector = embed_passages([passage])[0] if passage else None
        cache[key] = Profile(skills, Preferences.from_dict(preferences), vector)
    return cache[key]


def _summary(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = ("hit@1", "hit@3", "hit@5", "mrr", "ndcg@10", "recall@50")
    return {k: round(mean([r[k] for r in rows]), 4) for k in keys}


def evaluate(
    db: Session,
    cases: list[LabelledCase],
    config: RunConfig,
    today: date | None = None,
    on_case: Callable[[LabelledCase, list[int]], None] | None = None,
) -> dict[str, Any]:
    settings = config.search_config()
    profiles: dict[str, Profile] = {}
    rows: list[dict[str, Any]] = []
    elapsed = 0.0
    for case in cases:
        profile = make_profile(case.profile, profiles) if config.personalize else None
        started = time.perf_counter()
        results = search(
            db,
            case.query,
            profile=profile,
            mode=config.mode,
            config=settings,
            limit=50,
            today=today,
        )
        elapsed += time.perf_counter() - started
        ranked = [h.job.id for h in results.hits]
        if on_case:
            on_case(case, ranked)
        rows.append(
            {
                "slice": case.slice,
                "hit@1": hit_at(ranked, case.relevant, 1),
                "hit@3": hit_at(ranked, case.relevant, 3),
                "hit@5": hit_at(ranked, case.relevant, 5),
                "mrr": reciprocal_rank(ranked, case.relevant),
                "ndcg@10": ndcg_at(ranked, case.relevant, 10),
                # Candidate stage: what fusion hands to the re-ranker.
                "recall@50": recall_at(results.candidate_ids, case.relevant, 50),
            }
        )
    slices = sorted({r["slice"] for r in rows})
    return {
        "name": config.name,
        "cases": len(rows),
        "overall": _summary(rows),
        "slices": {s: _summary([r for r in rows if r["slice"] == s]) for s in slices},
        "ms_per_query": round(elapsed * 1000 / max(1, len(rows)), 1),
        # Per-case scores, in case order, for intervals and paired comparisons.
        "per_case": rows,
    }


def intervals(result: dict[str, Any]) -> dict[str, tuple[float, float]]:
    rows = result["per_case"]
    return {k: interval([r[k] for r in rows]) for k in INTERVAL_METRICS}


def compare(
    result: dict[str, Any], base: dict[str, Any], metric: str
) -> tuple[float, float, float]:
    """Paired difference in `metric` between two runs over the same cases."""
    return paired_difference(
        [r[metric] for r in result["per_case"]], [r[metric] for r in base["per_case"]]
    )


def stored(result: dict[str, Any]) -> dict[str, Any]:
    """The result without per-case rows, for the database."""
    return {k: v for k, v in result.items() if k != "per_case"}
