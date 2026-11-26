"""Markdown tables, written into marked sections of docs/EVALS.md."""

import re
from pathlib import Path
from typing import Any

from evals.harness import INTERVAL_METRICS, compare, intervals

EVALS_DOC = Path("/srv/docs/EVALS.md")
COLUMNS = ("hit@1", "hit@3", "hit@5", "mrr", "ndcg@10", "recall@50")


def retrieval_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| Configuration | hit@1 | hit@3 | hit@5 | MRR | nDCG@10 | recall@50 |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        cells = " | ".join(f"{result['overall'][c]:.3f}" for c in COLUMNS)
        lines.append(f"| {result['name']} | {cells} |")
    return "\n".join(lines)


def interval_table(results: list[dict[str, Any]]) -> str:
    """Each metric with its bootstrap 95% interval in brackets."""
    names = {"hit@1": "hit@1", "hit@5": "hit@5", "mrr": "MRR", "ndcg@10": "nDCG@10"}
    header = " | ".join(names[m] for m in INTERVAL_METRICS)
    lines = [
        f"| Configuration | {header} | recall@50 |",
        "|---|" + "---|" * (len(INTERVAL_METRICS) + 1),
    ]
    for result in results:
        bounds = intervals(result)
        cells = " | ".join(
            f"{result['overall'][m]:.3f} [{bounds[m][0]:.2f}, {bounds[m][1]:.2f}]"
            for m in INTERVAL_METRICS
        )
        lines.append(f"| {result['name']} | {cells} | {result['overall']['recall@50']:.3f} |")
    return "\n".join(lines)


def difference_table(
    results: list[dict[str, Any]], base: dict[str, Any], metrics: tuple[str, ...]
) -> str:
    """Paired differences against `base`. An interval that excludes zero is marked."""
    lines = [
        f"| Compared with {base['name']} | " + " | ".join(metrics) + " |",
        "|---|" + "---|" * len(metrics),
    ]
    for result in results:
        if result is base:
            continue
        cells = []
        for metric in metrics:
            diff, low, high = compare(result, base, metric)
            clear = low > 0 or high < 0
            cells.append(f"{diff:+.3f} [{low:+.2f}, {high:+.2f}]{' *' if clear else ''}")
        lines.append(f"| {result['name']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def update_section(name: str, body: str, path: Path = EVALS_DOC) -> None:
    """Replace the text between `<!-- name:start -->` and `<!-- name:end -->`."""
    if not path.exists():
        print(f"{path} not found; section '{name}' was printed only.")
        return
    text = path.read_text("utf-8")
    pattern = re.compile(rf"(<!-- {name}:start -->\n).*?(<!-- {name}:end -->)", re.DOTALL)
    if not pattern.search(text):
        raise ValueError(f"No '{name}' section in {path}")
    updated = pattern.sub(lambda m: f"{m[1]}{body}\n{m[2]}", text)
    path.write_text(updated, "utf-8")
