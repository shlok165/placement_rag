"""Ranking metrics with binary relevance."""

import math
from collections.abc import Sequence


def hit_at(ranked: Sequence[int], relevant: set[int], k: int) -> float:
    return 1.0 if any(i in relevant for i in ranked[:k]) else 0.0


def reciprocal_rank(ranked: Sequence[int], relevant: set[int]) -> float:
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at(ranked: Sequence[int], relevant: set[int], k: int = 10) -> float:
    gain = sum(
        1.0 / math.log2(position + 1)
        for position, item in enumerate(ranked[:k], start=1)
        if item in relevant
    )
    ideal = sum(1.0 / math.log2(p + 1) for p in range(1, min(k, len(relevant)) + 1))
    return gain / ideal if ideal else 0.0


def recall_at(ranked: Sequence[int], relevant: set[int], k: int) -> float:
    return len(relevant.intersection(ranked[:k])) / len(relevant) if relevant else 0.0


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
