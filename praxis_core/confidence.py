"""Confidence on one scale, and the checks a distribution must pass.

Praxis confidence is **one minus normalised entropy** of the calibrated distribution:
``1 - H(p) / log(n)``. A one-hot distribution scores 1.0, a uniform one 0.0, and the
formula is the same for a two-way boolean, a four-level score and a twenty-way choice,
which is what makes a single threshold comparable across question types and across
providers (plan §3.2, decision 1).

Whatever a provider reports as its own confidence is kept beside it as
``native_confidence`` and never used for routing.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .contracts import Distribution, is_finite


def entropy(distribution: Mapping[str, float]) -> float:
    """Shannon entropy in nats. Zero-probability terms contribute nothing."""
    total = 0.0
    for p in distribution.values():
        if p > 0.0:
            total -= p * math.log(p)
    return total


def confidence(distribution: Mapping[str, float]) -> float:
    """``1 - H(p)/log(n)``, clamped to ``[0, 1]``. A single-key distribution is 1.0."""
    n = len(distribution)
    if n <= 1:
        return 1.0
    value = 1.0 - entropy(distribution) / math.log(n)
    return min(1.0, max(0.0, value))


def check_distribution(candidate: object, keys: Sequence[str], tolerance: float = 1e-6) -> tuple[bool, str]:
    """Is this a probability distribution over exactly these keys? Defensive by design:
    it is fed whatever an adapter returned, which may be anything."""
    if not isinstance(candidate, Mapping):
        return False, f"distribution is not a mapping, got {type(candidate).__name__}"
    expected = set(keys)
    got = set(candidate.keys())
    if got != expected:
        missing, extra = sorted(expected - got), sorted(str(k) for k in got - expected)
        return False, f"distribution keys do not match the question: missing {missing}, extra {extra}"
    total = 0.0
    for key, value in candidate.items():
        if not is_finite(value):
            return False, f"probability for {key!r} is not a finite number: {value!r}"
        if value < 0.0:
            return False, f"probability for {key!r} is negative: {value!r}"
        total += float(value)
    if abs(total - 1.0) > tolerance:
        return False, f"distribution sums to {total:.6f}, not 1"
    return True, ""


def normalise(distribution: Mapping[str, float]) -> Distribution:
    """Rescale to sum to one. An all-zero input becomes uniform."""
    total = sum(max(0.0, float(v)) for v in distribution.values())
    if total <= 0.0:
        n = len(distribution)
        return {str(k): 1.0 / n for k in distribution} if n else {}
    return {str(k): max(0.0, float(v)) / total for k, v in distribution.items()}


def uniform(keys: Sequence[str]) -> Distribution:
    n = len(keys)
    return {k: 1.0 / n for k in keys} if n else {}


def one_hot(keys: Sequence[str], key: str) -> Distribution:
    if key not in keys:
        raise ValueError(f"{key!r} is not one of {list(keys)}")
    return {k: (1.0 if k == key else 0.0) for k in keys}


def argmax(distribution: Mapping[str, float], keys: Sequence[str]) -> str:
    """The most probable key. Ties go to the earlier key in declared order."""
    best, best_p = keys[0], -1.0
    for key in keys:
        p = float(distribution.get(key, 0.0))
        if p > best_p:
            best, best_p = key, p
    return best


def rank(distribution: Mapping[str, float], keys: Sequence[str]) -> list[str]:
    """Keys sorted most probable first; ties keep declared order."""
    order = {k: i for i, k in enumerate(keys)}
    return sorted(keys, key=lambda k: (-float(distribution.get(k, 0.0)), order[k]))


def expected_value(distribution: Mapping[str, float], keys: Sequence[str]) -> float:
    """For ordered levels: the probability-weighted level index."""
    return sum(i * float(distribution.get(k, 0.0)) for i, k in enumerate(keys))
