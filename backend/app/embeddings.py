"""Local sentence embeddings (ONNX, CPU). No text leaves the machine."""

import os
import threading
from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.core.config import get_settings

# Recommended by the model authors for short queries against longer passages.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_MAX_CHARS = 2_000
_lock = threading.Lock()


@lru_cache
def _model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(
        settings.embedding_model,
        cache_dir=str(settings.embedding_cache_dir),
        local_files_only=True,
        threads=min(4, os.cpu_count() or 1),
    )


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _lock:
        vectors = list(_model().embed([t[:_MAX_CHARS] for t in texts], batch_size=32))
    return [np.asarray(v, dtype=float).tolist() for v in vectors]


@lru_cache(maxsize=512)
def _embed_query_cached(text: str) -> tuple[float, ...]:
    with _lock:
        vector = next(iter(_model().embed([_QUERY_PREFIX + text])))
    return tuple(np.asarray(vector, dtype=float).tolist())


def embed_query(text: str) -> list[float]:
    return list(_embed_query_cached(text[:_MAX_CHARS]))


def warm_up() -> None:
    embed_query("warm up")
