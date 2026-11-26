"""Bootstrap confidence intervals over cases (1000 resamples, fixed seed)."""

from collections.abc import Sequence

import numpy as np

RESAMPLES = 1000
SEED = 7


def _draws(n: int, resamples: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n, size=(resamples, n))


def interval(
    values: Sequence[float], resamples: int = RESAMPLES, seed: int = SEED
) -> tuple[float, float]:
    """95% percentile interval of the mean."""
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return 0.0, 0.0
    means = data[_draws(data.size, resamples, seed)].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def paired_difference(
    first: Sequence[float], second: Sequence[float], resamples: int = RESAMPLES, seed: int = SEED
) -> tuple[float, float, float]:
    """Mean of first minus second on the same cases, with its 95% interval.

    Resampling cases in pairs keeps the per-query difficulty, so this is much tighter than
    comparing two separate intervals.
    """
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    if a.shape != b.shape:
        raise ValueError("Paired samples must be the same length.")
    diff = a - b
    if diff.size == 0:
        return 0.0, 0.0, 0.0
    means = diff[_draws(diff.size, resamples, seed)].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(diff.mean()), float(low), float(high)
