"""Combine ranked lists into one."""

from app.search.config import FusionConfig

Ranked = list[tuple[int, float]]


def reciprocal_rank(lists: list[tuple[Ranked, float]], k: int) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked, weight in lists:
        for position, (job_id, _) in enumerate(ranked, start=1):
            scores[job_id] = scores.get(job_id, 0.0) + weight / (k + position)
    return scores


def weighted_sum(lists: list[tuple[Ranked, float]]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked, weight in lists:
        if not ranked:
            continue
        values = [score for _, score in ranked]
        low, high = min(values), max(values)
        spread = high - low
        for job_id, score in ranked:
            scaled = (score - low) / spread if spread > 0 else 1.0
            scores[job_id] = scores.get(job_id, 0.0) + weight * scaled
    return scores


def fuse(semantic: Ranked, keyword: Ranked, config: FusionConfig) -> Ranked:
    lists = [(semantic, config.semantic_weight), (keyword, config.keyword_weight)]
    active = [(ranked, weight) for ranked, weight in lists if weight > 0]
    if config.method == "rrf":
        scores = reciprocal_rank(active, config.rrf_k)
    else:
        scores = weighted_sum(active)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
