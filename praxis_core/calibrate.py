"""Temperature calibration, one temperature per (question type, option count).

Every provider reports probabilities on its own terms: one ships over-confident, another
under-confident, a third reports a "level" instead of a number. Praxis puts them all on
one scale by fitting a single temperature ``T`` per (type, option count) on traces that
carry both the raw System-1 distribution and the System-2 label, then applying

    q_i ∝ p_i ^ (1/T)

before confidence is computed. ``T > 1`` softens an over-confident model, ``T < 1``
sharpens an under-confident one, ``T = 1`` is the identity. The fit minimises the
negative log-likelihood of the labels with a one-dimensional golden-section search, so
it needs no gradients, no dependency, and finishes in milliseconds on a few hundred
traces (Rung A of the training ladder, plan §3.6).

A distribution whose (type, option count) has not been fitted passes through unchanged
and is reported as ``calibrated = False``, so a threshold applied to it is applied to the
provider's own scale, and the trace says so.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .contracts import Distribution, Question, TraceEvent, stable_hash

_EPS = 1e-9
_GROUP_SEP = "/"


def _group_key(question: Question) -> tuple[str, int]:
    q = question.as_choice()
    return q.type, q.option_count


def scale(distribution: Mapping[str, float], keys: Sequence[str], temperature: float) -> Distribution:
    """``softmax(log p / T)`` over ``keys``, computed stably."""
    logits = [math.log(max(float(distribution.get(k, 0.0)), _EPS)) / temperature for k in keys]
    top = max(logits)
    weights = [math.exp(z - top) for z in logits]
    total = sum(weights)
    return {k: w / total for k, w in zip(keys, weights)}


def negative_log_likelihood(items: Sequence[tuple[Distribution, str]], keys_of: Sequence[Sequence[str]],
                            temperature: float) -> float:
    total = 0.0
    for (distribution, label), keys in zip(items, keys_of):
        total -= math.log(max(scale(distribution, keys, temperature).get(label, 0.0), _EPS))
    return total / max(1, len(items))


def fit_temperature(items: Sequence[tuple[Distribution, str]], keys_of: Sequence[Sequence[str]],
                    t_min: float = 0.05, t_max: float = 50.0, iterations: int = 80) -> float:
    """Golden-section search over ``log T``. Deterministic; no dependency."""
    lo, hi = math.log(t_min), math.log(t_max)
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fa = negative_log_likelihood(items, keys_of, math.exp(a))
    fb = negative_log_likelihood(items, keys_of, math.exp(b))
    for _ in range(iterations):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - phi * (hi - lo)
            fa = negative_log_likelihood(items, keys_of, math.exp(a))
        else:
            lo, a, fa = a, b, fb
            b = lo + phi * (hi - lo)
            fb = negative_log_likelihood(items, keys_of, math.exp(b))
    return math.exp((lo + hi) / 2.0)


def expected_calibration_error(max_probabilities: Sequence[float], corrects: Sequence[bool], bins: int = 10) -> float:
    """Reliability gap: |accuracy - confidence| averaged over equal-width bins, weighted by count."""
    if len(max_probabilities) != len(corrects):
        raise ValueError("one correctness flag per probability")
    n = len(max_probabilities)
    if n == 0:
        return 0.0
    sums = [[0.0, 0.0, 0] for _ in range(bins)]
    for p, ok in zip(max_probabilities, corrects):
        index = min(bins - 1, max(0, int(p * bins)))
        sums[index][0] += p
        sums[index][1] += 1.0 if ok else 0.0
        sums[index][2] += 1
    return sum(abs(acc / count - conf / count) * count / n for conf, acc, count in sums if count)


class TemperatureCalibrator:
    """The ``Calibrator`` port, fitted per (question type, option count)."""

    name = "temperature"

    def __init__(self, min_examples: int = 10, temperatures: Mapping[str, float] | None = None) -> None:
        self.min_examples = min_examples
        self._temperatures: dict[tuple[str, int], float] = {}
        self._skipped: dict[str, int] = {}
        for key, value in (temperatures or {}).items():
            kind, _, count = key.partition(_GROUP_SEP)
            self._temperatures[(kind, int(count))] = float(value)

    @property
    def version(self) -> str:
        if not self._temperatures:
            return f"{self.name}-v1/unfitted"
        return f"{self.name}-v1/{stable_hash(self.temperatures())}"

    def temperatures(self) -> dict[str, float]:
        return {f"{kind}{_GROUP_SEP}{count}": t for (kind, count), t in sorted(self._temperatures.items())}

    @property
    def skipped(self) -> dict[str, int]:
        """Groups seen in the last ``fit`` with too few labelled traces to fit, and their counts."""
        return dict(self._skipped)

    def fit(self, traces: Sequence[TraceEvent]) -> Mapping[str, float]:
        groups: dict[tuple[str, int], list[tuple[Distribution, str]]] = {}
        keys_of: dict[tuple[str, int], list[Sequence[str]]] = {}
        for trace in traces:
            for q in trace.questions:
                if q.raw_distribution is None or q.system2_answer is None:
                    continue
                question = q.question.as_choice()
                try:
                    label = q.question.key_for(q.system2_answer)   # a rank answer maps to its top key
                except ValueError:
                    continue
                group = _group_key(question)
                groups.setdefault(group, []).append((q.raw_distribution, label))
                keys_of.setdefault(group, []).append(question.keys())
        self._skipped = {}
        for group, items in groups.items():
            if len(items) < self.min_examples:
                self._skipped[f"{group[0]}{_GROUP_SEP}{group[1]}"] = len(items)
                continue
            self._temperatures[group] = fit_temperature(items, keys_of[group])
        return self.temperatures()

    def apply(self, question: Question, distribution: Mapping[str, float]) -> Distribution:
        keys = question.keys()
        temperature = self._temperatures.get(_group_key(question))
        if temperature is None:
            return {k: float(distribution.get(k, 0.0)) for k in keys}
        return scale(distribution, keys, temperature)

    def is_fitted(self, question: Question) -> bool:
        return _group_key(question) in self._temperatures

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "min_examples": self.min_examples, "temperatures": self.temperatures()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TemperatureCalibrator:
        return cls(int(data.get("min_examples", 10)), dict(data.get("temperatures") or {}))
