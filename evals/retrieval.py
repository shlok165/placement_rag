"""Retrieval evals: compare configurations, sweep weights, guard the baseline.

python -m evals.retrieval            run, print tables, update docs/EVALS.md
python -m evals.retrieval --check    run and fail if hit@5 drops below the baseline
python -m evals.retrieval --misses   also list the cases with nothing relevant in the top 5
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.db.models import EvalRun
from app.db.session import get_sessionmaker
from app.search.config import get_search_config
from evals.corpus import labelled_cases, load_jobs
from evals.dataset import REFERENCE_DATE
from evals.evaldb import eval_session
from evals.harness import STANDARD_CONFIGS, LabelledCase, RunConfig, evaluate
from evals.report import retrieval_table, update_section

BASELINE = Path(__file__).with_name("baseline.json")
GUARDED = "Hybrid + personal re-rank"
TOLERANCE = 0.0001


def sweep_configs() -> list[RunConfig]:
    configs = []
    pairs = ((1.0, 1.0), (1.0, 0.5), (1.0, 0.25), (0.5, 1.0))
    for method, k in (("rrf", 10), ("rrf", 60), ("weighted", 60)):
        label = f"RRF k={k}" if method == "rrf" else "Weighted sum"
        for semantic, keyword in pairs:
            configs.append(
                RunConfig(
                    f"{label}, semantic {semantic}, keyword {keyword}",
                    overrides={
                        "fusion.method": method,
                        "fusion.rrf_k": k,
                        "fusion.semantic_weight": semantic,
                        "fusion.keyword_weight": keyword,
                    },
                )
            )
    return configs


def rerank_configs() -> list[RunConfig]:
    configs = []
    for relevance in (0.45, 0.7, 1.0, 1.5):
        for skills, preferences in ((0.1, 0.2), (0.2, 0.2), (0.2, 0.3), (0.3, 0.2)):
            configs.append(
                RunConfig(
                    f"relevance {relevance}, skills {skills}, preferences {preferences}",
                    personalize=True,
                    overrides={
                        "rerank.relevance": relevance,
                        "rerank.skills": skills,
                        "rerank.preferences": preferences,
                    },
                )
            )
    return configs


def _save(
    results: list[dict[str, Any]], unseen: list[dict[str, Any]], sweep: list[dict[str, Any]]
) -> None:
    with get_sessionmaker()() as db:
        db.add(
            EvalRun(
                kind="retrieval",
                config={
                    "corpus": "synthetic, isolated database",
                    "search": get_search_config().model_dump(),
                },
                metrics={"configs": results, "held_out": unseen, "sweep": sweep},
            )
        )
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals.retrieval")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--misses", action="store_true")
    args = parser.parse_args()

    with eval_session() as db:
        ids = load_jobs(db, REFERENCE_DATE)
        keys = {v: k for k, v in ids.items()}
        cases = labelled_cases(ids, REFERENCE_DATE)
        # Cases are ordered by slice, so taking every other one splits each slice in half.
        dev, held_out = cases[::2], cases[1::2]
        print(f"{len(ids)} synthetic postings, {len(cases)} labelled cases\n")

        def show_miss(case: LabelledCase, ranked: list[int]) -> None:
            if not case.relevant.intersection(ranked[:5]):
                top = ", ".join(keys[i] for i in ranked[:5])
                print(f"  miss [{case.slice}] {case.query!r}: {top}")

        results = []
        for config in STANDARD_CONFIGS:
            report = show_miss if args.misses else None
            results.append(evaluate(db, cases, config, REFERENCE_DATE, report))
        print(retrieval_table(results))
        unseen = [evaluate(db, held_out, c, REFERENCE_DATE) for c in STANDARD_CONFIGS]
        print("\nHeld-out half\n" + retrieval_table(unseen))
        sweep: list[dict[str, Any]] = []
        rerank: list[dict[str, Any]] = []
        if not args.check:
            sweep = [evaluate(db, dev, c, REFERENCE_DATE) for c in sweep_configs()]
            rerank = [evaluate(db, dev, c, REFERENCE_DATE) for c in rerank_configs()]
            print("\nFusion sweep\n" + retrieval_table(sweep))
            print("\nRe-rank sweep\n" + retrieval_table(rerank))

    guarded = next(r for r in results if r["name"] == GUARDED)["overall"]["hit@5"]
    if args.check:
        floor = json.loads(BASELINE.read_text("utf-8"))["hit@5"]
        print(f"\nhit@5 {guarded:.4f}, baseline {floor:.4f}")
        if guarded + TOLERANCE < floor:
            print("hit@5 dropped below the committed baseline.", file=sys.stderr)
            return 1
        return 0

    update_section("retrieval", _section(results, unseen, sweep, rerank, len(ids)))
    try:
        _save(results, unseen, sweep + rerank)
    except Exception as exc:
        print(f"Run not stored ({type(exc).__name__}); the application database is not migrated.")
    print(f"\nLLM mode: {get_settings().llm_mode}. Retrieval evals make no LLM calls.")
    return 0


def _section(
    results: list[dict[str, Any]],
    unseen: list[dict[str, Any]],
    sweep: list[dict[str, Any]],
    rerank: list[dict[str, Any]],
    job_count: int,
) -> str:
    cases = results[0]["cases"]
    parts = [
        f"{job_count} synthetic postings, {cases} labelled query and profile pairs. No LLM calls.",
        "",
        f"### Held-out half ({unseen[0]['cases']} cases, not used to choose weights)",
        "",
        retrieval_table(unseen),
        "",
        f"### All {cases} cases",
        "",
        retrieval_table(results),
        "",
    ]
    for name in sorted(results[0]["slices"]):
        rows = [{"name": r["name"], "overall": r["slices"][name]} for r in results]
        parts += [f"### Slice: {name}", "", retrieval_table(rows), ""]
    parts += [
        "### Fusion weight sweep (hybrid, no re-rank, development half)",
        "",
        retrieval_table(sweep),
        "",
        "### Re-rank weight sweep (hybrid + personal re-rank, development half)",
        "",
        retrieval_table(rerank),
    ]
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())
