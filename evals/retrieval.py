"""Retrieval evals: compare configurations, sweep weights, guard the baseline.

python -m evals.retrieval            main set, held-out half with intervals, messy text, sweeps
python -m evals.retrieval --check    run and fail if hit@5 drops below the baseline
python -m evals.retrieval --misses   also list the cases with nothing relevant in the top 5
python -m evals.retrieval --cross    cross-encoder experiment, development half only
python -m evals.retrieval --blind --release v1.0.0   the blind set, once per release
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.db.models import EvalRun
from app.db.session import get_sessionmaker
from app.search.config import get_search_config
from evals.blind.cases import build_blind_cases
from evals.blind.dataset import BLIND
from evals.corpus import labelled_cases, load_jobs
from evals.dataset import REFERENCE_DATE
from evals.evaldb import eval_session
from evals.harness import (
    STANDARD_CONFIGS,
    LabelledCase,
    RunConfig,
    compare,
    evaluate,
    stored,
)
from evals.noise import noisy
from evals.report import difference_table, interval_table, retrieval_table, update_section

BASELINE = Path(__file__).with_name("baseline.json")
BLIND_LOG = Path(__file__).parent / "blind" / "runs.jsonl"
GUARDED = "Hybrid + personal re-rank"
TOLERANCE = 0.0001
CROSS = {"cross_encoder.enabled": True}
CROSS_CONFIGS = [
    RunConfig("Hybrid + cross-encoder", overrides=CROSS),
    RunConfig("Hybrid + cross-encoder + personal re-rank", personalize=True, overrides=CROSS),
]
DIFF_METRICS = ("hit@5", "ndcg@10")


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


def _save(kind: str, metrics: dict[str, Any]) -> None:
    try:
        with get_sessionmaker()() as db:
            config = {
                "corpus": "synthetic, isolated database",
                "search": get_search_config().model_dump(),
            }
            db.add(EvalRun(kind=kind, config=config, metrics=metrics))
            db.commit()
    except Exception as exc:
        print(f"Run not stored ({type(exc).__name__}); the application database is not migrated.")


def _by_name(results: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(r for r in results if r["name"] == name)


# ---------------------------------------------------------------- main set


def run_main(check: bool, misses: bool) -> int:
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

        report = show_miss if misses else None
        results = [evaluate(db, cases, c, REFERENCE_DATE, report) for c in STANDARD_CONFIGS]
        print(interval_table(results))
        unseen = [evaluate(db, held_out, c, REFERENCE_DATE) for c in STANDARD_CONFIGS]
        print("\nHeld-out half\n" + interval_table(unseen))

        guarded = _by_name(results, GUARDED)["overall"]["hit@5"]
        if check:
            floor = json.loads(BASELINE.read_text("utf-8"))["hit@5"]
            print(f"\nhit@5 {guarded:.4f}, baseline {floor:.4f}")
            if guarded + TOLERANCE < floor:
                print("hit@5 dropped below the committed baseline.", file=sys.stderr)
                return 1
            return 0

        sweep = [evaluate(db, dev, c, REFERENCE_DATE) for c in sweep_configs()]
        rerank = [evaluate(db, dev, c, REFERENCE_DATE) for c in rerank_configs()]
        print("\nFusion sweep\n" + retrieval_table(sweep))
        print("\nRe-rank sweep\n" + retrieval_table(rerank))

    messy = run_messy()
    print("\nMessy text\n" + messy_table(results, messy))
    update_section("retrieval", _section(results, unseen, sweep, rerank, messy, len(ids)))
    _save(
        "retrieval",
        {
            "configs": [stored(r) for r in results],
            "held_out": [stored(r) for r in unseen],
            "messy": [stored(r) for r in messy],
            "sweep": [stored(r) for r in sweep + rerank],
        },
    )
    print(f"\nLLM mode: {get_settings().llm_mode}. Retrieval evals make no LLM calls.")
    return 0


def run_messy() -> list[dict[str, Any]]:
    """The same cases over the same postings after deterministic noise."""
    with eval_session() as db:
        ids = load_jobs(db, REFERENCE_DATE, transform=noisy)
        cases = labelled_cases(ids, REFERENCE_DATE)
        return [evaluate(db, cases, c, REFERENCE_DATE) for c in STANDARD_CONFIGS]


def messy_table(clean: list[dict[str, Any]], messy: list[dict[str, Any]]) -> str:
    lines = [
        "| Configuration | nDCG@10 clean | messy | change [95% CI] "
        "| hit@5 clean | messy | change |",
        "|---|---|---|---|---|---|---|",
    ]
    for before, after in zip(clean, messy, strict=True):
        ndcg = compare(after, before, "ndcg@10")
        hit = compare(after, before, "hit@5")
        lines.append(
            f"| {before['name']} | {before['overall']['ndcg@10']:.3f} | "
            f"{after['overall']['ndcg@10']:.3f} | "
            f"{ndcg[0]:+.3f} [{ndcg[1]:+.2f}, {ndcg[2]:+.2f}] | "
            f"{before['overall']['hit@5']:.3f} | {after['overall']['hit@5']:.3f} | {hit[0]:+.3f} |"
        )
    return "\n".join(lines)


def _section(
    results: list[dict[str, Any]],
    unseen: list[dict[str, Any]],
    sweep: list[dict[str, Any]],
    rerank: list[dict[str, Any]],
    messy: list[dict[str, Any]],
    job_count: int,
) -> str:
    cases = results[0]["cases"]
    semantic = _by_name(unseen, "Semantic only")
    parts = [
        f"{job_count} synthetic postings, {cases} labelled query and profile pairs. No LLM calls. "
        "Brackets hold bootstrap 95% intervals over cases (1000 resamples, seed 7).",
        "",
        f"### Held-out half ({unseen[0]['cases']} cases, not used to choose weights)",
        "",
        interval_table(unseen),
        "",
        "Paired differences on the same cases; * marks an interval that excludes zero.",
        "",
        difference_table(unseen, semantic, DIFF_METRICS),
        "",
        f"### All {cases} cases",
        "",
        interval_table(results),
        "",
    ]
    for name in sorted(results[0]["slices"]):
        rows = [{"name": r["name"], "overall": r["slices"][name]} for r in results]
        parts += [f"### Slice: {name}", "", retrieval_table(rows), ""]
    parts += [
        "### Messy text (all cases, same postings after deterministic noise)",
        "",
        messy_table(results, messy),
        "",
        "### Fusion weight sweep (hybrid, no re-rank, development half)",
        "",
        retrieval_table(sweep),
        "",
        "### Re-rank weight sweep (hybrid + personal re-rank, development half)",
        "",
        retrieval_table(rerank),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------- cross-encoder experiment


def run_cross() -> int:
    pairs = [("Hybrid", CROSS_CONFIGS[0]), (GUARDED, CROSS_CONFIGS[1])]
    base = {c.name: c for c in STANDARD_CONFIGS}
    with eval_session() as db:
        ids = load_jobs(db, REFERENCE_DATE)
        dev = labelled_cases(ids, REFERENCE_DATE)[::2]
        # Load the model and warm both paths before timing anything.
        evaluate(db, dev[:2], CROSS_CONFIGS[0], REFERENCE_DATE)
        evaluate(db, dev[:2], base["Hybrid"], REFERENCE_DATE)
        rows = []
        for name, crossed in pairs:
            rows.append(
                (
                    evaluate(db, dev, base[name], REFERENCE_DATE),
                    evaluate(db, dev, crossed, REFERENCE_DATE),
                )
            )
    text = cross_table(rows, f"development half, {len(dev)} cases")
    print(text)
    update_section("cross-encoder", text)
    _save("retrieval-cross", {"pairs": [[stored(a), stored(b)] for a, b in rows]})
    return 0


def cross_table(rows: list[tuple[dict[str, Any], dict[str, Any]]], label: str) -> str:
    lines = [
        f"Cross-encoder `{get_search_config().cross_encoder.model}` over the top "
        f"{get_search_config().cross_encoder.top_n} fused candidates ({label}).",
        "",
        "| Configuration | nDCG@10 | change [95% CI] | hit@5 | change | ms per query |",
        "|---|---|---|---|---|---|",
    ]
    for before, after in rows:
        for result, base in ((before, None), (after, before)):
            if base is None:
                change, hit = "", ""
            else:
                d = compare(result, base, "ndcg@10")
                change = f"{d[0]:+.3f} [{d[1]:+.2f}, {d[2]:+.2f}]"
                hit = f"{compare(result, base, 'hit@5')[0]:+.3f}"
            lines.append(
                f"| {result['name']} | {result['overall']['ndcg@10']:.3f} | {change} | "
                f"{result['overall']['hit@5']:.3f} | {hit} | {result['ms_per_query']:.0f} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------- blind set


def run_blind(release: str, force: bool) -> int:
    runs = (
        [json.loads(line) for line in BLIND_LOG.read_text("utf-8").splitlines() if line.strip()]
        if BLIND_LOG.exists()
        else []
    )
    if any(r["release"] == release for r in runs) and not force:
        print(
            f"The blind set was already run for {release}. It runs once per release.",
            file=sys.stderr,
        )
        return 1
    configs = [*STANDARD_CONFIGS, *CROSS_CONFIGS]
    with eval_session() as db:
        ids = load_jobs(db, REFERENCE_DATE, variant=BLIND)
        cases = labelled_cases(ids, REFERENCE_DATE, BLIND, build_blind_cases)
        results = []
        for config in configs:
            try:
                results.append(evaluate(db, cases, config, REFERENCE_DATE))
            except Exception as exc:  # the cross-encoder model may be missing offline
                print(f"{config.name} skipped: {type(exc).__name__}")
    semantic = _by_name(results, "Semantic only")
    text = "\n".join(
        [
            f"Release {release}, run {datetime.now(UTC).date().isoformat()}. "
            f"{len(ids)} blind synthetic postings, {len(cases)} cases "
            f"({', '.join(f'{n} {s}' for s, n in _slice_counts(cases).items())}). No LLM calls.",
            "",
            interval_table(results),
            "",
            "Paired differences on the same cases; * marks an interval that excludes zero.",
            "",
            difference_table(results, semantic, DIFF_METRICS),
        ]
    )
    print(text)
    update_section("blind", text)
    BLIND_LOG.parent.mkdir(exist_ok=True)
    with BLIND_LOG.open("a", encoding="utf-8") as log:
        entry = {
            "release": release,
            "date": datetime.now(UTC).date().isoformat(),
            "search": get_search_config().model_dump(),
            "results": {r["name"]: r["overall"] for r in results},
        }
        log.write(json.dumps(entry) + "\n")
    _save("retrieval-blind", {"release": release, "configs": [stored(r) for r in results]})
    return 0


def _slice_counts(cases: list[LabelledCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.slice] = counts.get(case.slice, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals.retrieval")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--misses", action="store_true")
    parser.add_argument("--cross", action="store_true")
    parser.add_argument("--blind", action="store_true")
    parser.add_argument("--release", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.blind:
        if not args.release:
            print("Name the release, for example --release v1.0.0.", file=sys.stderr)
            return 1
        return run_blind(args.release, args.force)
    if args.cross:
        return run_cross()
    return run_main(args.check, args.misses)


if __name__ == "__main__":
    sys.exit(main())
