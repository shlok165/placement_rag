"""Optional cross-encoder stage: reorders the top fused candidates. Off by default.

The fused scores are kept and handed out again in the new order, so the re-rank that follows sees
the same scale whether this stage ran or not.
"""

import os
import threading
from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.core.config import get_settings
from app.db.models import Job
from app.search.config import CrossEncoderConfig

_lock = threading.Lock()


@lru_cache
def _model(name: str) -> TextCrossEncoder:
    return TextCrossEncoder(
        name,
        cache_dir=str(get_settings().embedding_cache_dir),
        local_files_only=os.environ.get("HF_HUB_OFFLINE") == "1",
        threads=min(4, os.cpu_count() or 1),
    )


def passage(job: Job) -> str:
    return f"{job.title}. {job.company}. {', '.join(job.skills)}. {job.description[:600]}"


def reorder(
    query: str, ranked: list[tuple[int, float]], pool: dict[int, Job], config: CrossEncoderConfig
) -> list[tuple[int, float]]:
    head, tail = ranked[: config.top_n], ranked[config.top_n :]
    if len(head) < 2:
        return ranked
    with _lock:
        scores = list(_model(config.model).rerank(query, [passage(pool[i]) for i, _ in head]))
    order = sorted(range(len(head)), key=lambda i: (-scores[i], head[i][0]))
    values = sorted((s for _, s in head), reverse=True)
    return [(head[i][0], value) for i, value in zip(order, values, strict=True)] + tail
