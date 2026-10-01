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

For a student that reports **one number** (a generative student's self-reported
confidence) the sibling is ``PlattCalibrator``: a two-parameter logistic fit,
``p = sigmoid(a · logit(c) + b)``, on (confidence, matched the label) pairs, solved by
Newton's method with a little ridge so a perfectly separable sample cannot blow up.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

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
    return {k: w / total for k, w in zip(keys, weights, strict=False)}


def negative_log_likelihood(
    items: Sequence[tuple[Distribution, str]], keys_of: Sequence[Sequence[str]], temperature: float
) -> float:
    total = 0.0
    for (distribution, label), keys in zip(items, keys_of, strict=False):
        total -= math.log(max(scale(distribution, keys, temperature).get(label, 0.0), _EPS))
    return total / max(1, len(items))


def fit_temperature(
    items: Sequence[tuple[Distribution, str]],
    keys_of: Sequence[Sequence[str]],
    t_min: float = 0.05,
    t_max: float = 50.0,
    iterations: int = 80,
) -> float:
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
    for p, ok in zip(max_probabilities, corrects, strict=False):
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
                    label = q.question.key_for(q.system2_answer)  # a rank answer maps to its top key
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


# ------------------------------------------------------------------ scalar scores


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def logit(p: float, eps: float = 1e-6) -> float:
    p = min(1.0 - eps, max(eps, p))
    return math.log(p / (1.0 - p))


def _platt_nll(xs: Sequence[float], ys: Sequence[float], a: float, b: float, ridge: float) -> float:
    total = 0.5 * ridge * ((a - 1.0) ** 2 + b * b)
    for x, y in zip(xs, ys, strict=False):
        z = a * x + b
        # log(1 + exp(z)) computed stably, minus y*z
        total += (max(z, 0.0) + math.log1p(math.exp(-abs(z)))) - y * z
    return total


def fit_platt(pairs: Sequence[tuple[float, bool]], ridge: float = 1e-3, iterations: int = 100) -> tuple[float, float]:
    """Logistic regression of "matched" on logit(confidence) with an intercept: returns (a, b).

    Damped Newton: each step is halved until the (ridge-regularised) negative
    log-likelihood goes down, so a saturated start cannot send the slope to infinity."""
    xs = [logit(c) for c, _ in pairs]
    ys = [1.0 if ok else 0.0 for _, ok in pairs]
    a, b = 1.0, 0.0
    current = _platt_nll(xs, ys, a, b, ridge)
    for _ in range(iterations):
        g_a = ridge * (a - 1.0)
        g_b = ridge * b
        h_aa, h_ab, h_bb = ridge, 0.0, ridge
        for x, y in zip(xs, ys, strict=False):
            p = sigmoid(a * x + b)
            w = p * (1.0 - p)
            g_a += (p - y) * x
            g_b += p - y
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        det = h_aa * h_bb - h_ab * h_ab
        if det <= 1e-12:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (h_aa * g_b - h_ab * g_a) / det
        step = 1.0
        improved = False
        for _ in range(30):
            na, nb = a - step * da, b - step * db
            candidate = _platt_nll(xs, ys, na, nb, ridge)
            if candidate < current:
                a, b, current, improved = na, nb, candidate, True
                break
            step *= 0.5
        if not improved or (abs(step * da) < 1e-9 and abs(step * db) < 1e-9):
            break
    return a, b


class PlattCalibrator:
    """The ``ScalarCalibrator`` port: one logistic map from a raw confidence to P(matched)."""

    name = "platt"

    def __init__(self, min_examples: int = 10, a: float | None = None, b: float | None = None) -> None:
        self.min_examples = min_examples
        self._params: tuple[float, float] | None = None if a is None or b is None else (a, b)
        self._skipped = 0

    @property
    def version(self) -> str:
        if self._params is None:
            return f"{self.name}-v1/unfitted"
        return f"{self.name}-v1/{stable_hash(self.parameters())}"

    def parameters(self) -> dict[str, float]:
        return {} if self._params is None else {"a": self._params[0], "b": self._params[1]}

    @property
    def skipped(self) -> int:
        """Usable pairs found in the last ``fit`` when it was below ``min_examples`` (else 0)."""
        return self._skipped

    @staticmethod
    def pairs_from(traces: Sequence[TraceEvent]) -> list[tuple[float, bool]]:
        pairs: list[tuple[float, bool]] = []
        for trace in traces:
            g = trace.generation
            if g is None or g.native_confidence is None or g.matched is None:
                continue
            pairs.append((float(g.native_confidence), bool(g.matched)))
        return pairs

    def fit(self, traces: Sequence[TraceEvent]) -> Mapping[str, float]:
        pairs = self.pairs_from(traces)
        if len(pairs) < self.min_examples or len({ok for _, ok in pairs}) < 2:
            self._skipped = len(pairs)
            return self.parameters()
        self._skipped = 0
        self._params = fit_platt(pairs)
        return self.parameters()

    def apply(self, confidence: float) -> float:
        c = min(1.0, max(0.0, float(confidence)))
        if self._params is None:
            return c
        a, b = self._params
        return sigmoid(a * logit(c) + b)

    def is_fitted(self) -> bool:
        return self._params is not None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "min_examples": self.min_examples, **self.parameters()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PlattCalibrator:
        a, b = data.get("a"), data.get("b")
        return cls(int(data.get("min_examples", 10)), None if a is None else float(a), None if b is None else float(b))
