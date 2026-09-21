"""Students. The interface, and one that runs anywhere.

A student is anything that answers a capability and says how sure it is. That is the
whole contract — `predict(inputs) -> (output, confidence)`.

Two implementations ship:

**NearestNeighbourStudent** — the baseline, and it is honest about being one. It stores
accepted traces and answers by nearest match over token overlap. No GPU, no training
run, no dependency. It exists so the flywheel is demonstrably closed end to end, and so
there is a number for a LoRA student to beat.

**LoraStudent** — the real one. It is a stub: the interface is fixed, `fit` raises
until a backend is wired in. It raises rather than silently falling back, because a
"trained" student that was never trained is exactly the confident-wrong failure this
project exists to prevent.
"""
from __future__ import annotations
from typing import Any, Protocol
import json, math


class Student(Protocol):
    def fit(self, traces: list) -> None: ...
    def predict(self, inputs: dict) -> tuple[Any, float]: ...


def _tokens(d: dict) -> set[str]:
    return set(json.dumps(d, sort_keys=True).lower().replace('"', " ").replace(":", " ")
               .replace(",", " ").replace("{", " ").replace("}", " ").split())


class NearestNeighbourStudent:
    """Baseline. Answers by closest accepted trace; confidence is the overlap."""

    name = "nearest-neighbour"

    def __init__(self) -> None:
        self._memory: list[tuple[set[str], dict, Any]] = []

    def fit(self, traces: list) -> None:
        self._memory = [(_tokens(t.inputs), t.inputs, t.output)
                        for t in traces if t.accepted]

    def predict(self, inputs: dict) -> tuple[Any, float]:
        if not self._memory:
            return None, 0.0
        q = _tokens(inputs)
        best, score = None, 0.0
        for toks, _, out in self._memory:
            union = len(q | toks)
            j = len(q & toks) / union if union else 0.0
            if j > score:
                best, score = out, j
        return best, round(score, 3)


class LoraStudent:
    """The real student. Interface fixed; backend not wired in.

    `fit` raises. It does not quietly fall back to the baseline, because a student that
    reports itself trained when it is not is the failure mode the whole project exists
    to prevent.
    """

    name = "lora"

    def __init__(self, base_model: str, rank: int = 8) -> None:
        self.base_model, self.rank = base_model, rank
        self._fitted = False

    def fit(self, traces: list) -> None:
        raise NotImplementedError(
            "LoraStudent.fit needs a training backend (peft + transformers) and a GPU. "
            "Use NearestNeighbourStudent for the baseline, and read docs/distillation.md "
            "before wiring one in.")

    def predict(self, inputs: dict) -> tuple[Any, float]:
        if not self._fitted:
            raise RuntimeError("this student was never fitted; refusing to answer")
        raise NotImplementedError
