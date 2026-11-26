"""Leave-one-out simulation of the taste feature. `python -m evals.taste`

Simulated students, not real ones. Each one has a profile and five saved postings: four from one
role family and one from another. One saved posting is hidden at a time, the taste vector is built
from the other four, and the hidden posting's rank among all other postings is compared with and
without the taste feature. It shows that the mechanism works on this data. It says nothing about
whether real students would benefit.
"""

import random
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models import Job
from app.embeddings import embed_passages
from app.ingest.indexing import job_passage
from app.search.config import RerankConfig, get_search_config
from app.search.matching import Preferences
from app.search.ranking import Profile, score_job
from app.search.taste import combine
from evals.cases import PROFILES
from evals.dataset import FAMILIES, REFERENCE_DATE, generate_jobs
from evals.report import update_section
from evals.stats import paired_difference

SEED = 20261128
LIKED = 5
STUDENTS_PER_FAMILY = 2
SENSITIVITY = (0.05, 0.2, 0.3)
# Which synthetic profile a student who likes this family would have.
FAMILY_PROFILE = {
    "backend": "software", "frontend": "software", "fullstack": "software", "mobile": "software",
    "security": "software", "qa": "software", "blockchain": "software", "devops": "fulltime",
    "data_engineering": "data", "data_science": "data", "analytics": "data", "finance": "data",
    "ml": "ml", "nlp": "ml", "vision": "ml", "embedded": "electronics", "vlsi": "electronics",
    "electrical": "electronics", "robotics": "mechanical", "mechanical": "mechanical",
    "thermal": "mechanical", "manufacturing": "mechanical", "chemical": "mechanical",
    "civil": "civil", "design": "product", "product": "product",
}  # fmt: skip


def corpus() -> tuple[list[Job], dict[int, str]]:
    rows = generate_jobs(REFERENCE_DATE)
    jobs = [Job(id=i + 1, **row.fields) for i, row in enumerate(rows)]
    for job, vector in zip(jobs, embed_passages([job_passage(j) for j in jobs]), strict=True):
        job.embedding = vector
    return jobs, {j.id: row.family for j, row in zip(jobs, rows, strict=True)}


def students(jobs: list[Job], family_of: dict[int, str]) -> list[dict[str, Any]]:
    by_family: dict[str, list[Job]] = {}
    for job in jobs:
        by_family.setdefault(family_of[job.id], []).append(job)
    people = []
    for index, family in enumerate(f.key for f in FAMILIES for _ in range(STUDENTS_PER_FAMILY)):
        rng = random.Random(SEED + index)
        other = rng.choice([f.key for f in FAMILIES if f.key != family])
        liked = rng.sample(by_family[family], LIKED - 1) + rng.sample(by_family[other], 1)
        people.append({"profile": PROFILES[FAMILY_PROFILE[family]], "liked": liked})
    return people


def ranks(
    jobs: list[Job], people: list[dict[str, Any]], config: RerankConfig, use_taste: bool
) -> list[int]:
    """Rank of each hidden posting, one per (student, hidden posting) pair."""
    now = datetime.combine(REFERENCE_DATE, datetime.min.time(), UTC)
    taste_config = get_search_config().taste
    out = []
    for person in people:
        spec = person["profile"]
        for hidden in person["liked"]:
            rest = [j for j in person["liked"] if j is not hidden]
            events = [
                ("save", now - timedelta(days=3 * k), list(j.embedding)) for k, j in enumerate(rest)
            ]
            profile = Profile(
                skills=list(spec["skills"]),
                preferences=Preferences.from_dict(spec["preferences"]),
                taste=combine(events, taste_config, now) if use_taste else None,
            )
            pool = [j for j in jobs if j not in rest]
            scored = sorted(
                pool,
                key=lambda j: (-score_job(j, profile, config, REFERENCE_DATE)["score"], j.id),
            )
            out.append(scored.index(hidden) + 1)
    return out


def summary(found: list[int]) -> dict[str, float]:
    n = len(found)
    return {
        "mrr": sum(1 / r for r in found) / n,
        "hit@5": sum(r <= 5 for r in found) / n,
        "hit@10": sum(r <= 10 for r in found) / n,
        "median_rank": sorted(found)[n // 2],
    }


def main() -> int:
    jobs, family_of = corpus()
    people = students(jobs, family_of)
    config = get_search_config().rerank
    base = ranks(jobs, people, config, use_taste=False)
    with_taste = ranks(jobs, people, config, use_taste=True)
    a, b = summary(base), summary(with_taste)
    rr = paired_difference([1 / r for r in with_taste], [1 / r for r in base])
    hit = paired_difference([float(r <= 10) for r in with_taste], [float(r <= 10) for r in base])
    lines = [
        f"Simulated students, not real ones: {len(people)} students, {LIKED} saved postings each "
        f"(four from one role family, one from another), {len(base)} leave-one-out trials over "
        f"{len(jobs)} synthetic postings. Ranking with no query, as on the home page. Taste weight "
        f"{config.taste}, set before this was run.",
        "",
        "| Ranking | MRR | hit@5 | hit@10 | median rank |",
        "|---|---|---|---|---|",
        f"| Profile only | {a['mrr']:.3f} | {a['hit@5']:.3f} | {a['hit@10']:.3f} | "
        f"{a['median_rank']:.0f} |",
        f"| Profile + taste | {b['mrr']:.3f} | {b['hit@5']:.3f} | {b['hit@10']:.3f} | "
        f"{b['median_rank']:.0f} |",
        "",
        f"Paired change: MRR {rr[0]:+.3f} [{rr[1]:+.2f}, {rr[2]:+.2f}], "
        f"hit@10 {hit[0]:+.3f} [{hit[1]:+.2f}, {hit[2]:+.2f}] (bootstrap 95%, trials resampled).",
        "",
        "Sensitivity to the weight (for reading only; the weight was not chosen from it):",
        "",
        "| Taste weight | MRR | hit@10 |",
        "|---|---|---|",
    ]
    for weight in SENSITIVITY:
        tried = summary(ranks(jobs, people, config.model_copy(update={"taste": weight}), True))
        lines.append(f"| {weight} | {tried['mrr']:.3f} | {tried['hit@10']:.3f} |")
    text = "\n".join(lines)
    print(text)
    update_section("taste", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
