"""Markdown tables, written into marked sections of docs/EVALS.md."""

import re
from pathlib import Path
from typing import Any

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
