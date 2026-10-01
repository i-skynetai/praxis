"""The nearest-neighbour baseline, migrated to the ``DecisionModel`` port.

It is the same idea as the original student (store what the teacher said, answer by
token overlap, no GPU, no dependency) expressed as a distribution instead of a single
answer with a similarity score. Per question, the ``k`` most similar remembered examples
vote with their Jaccard similarity; the vote is mixed with a uniform prior in proportion
to how weak the best match was:

    p = s · votes + (1 - s) · uniform        where s is the best similarity

and each neighbour's vote is its similarity cubed, so a near-duplicate outweighs a
handful of loose matches instead of being outvoted by them.

so a query that resembles nothing ends up uniform (Praxis confidence 0, which the router
never serves) and a near-duplicate ends up peaked. The best similarity itself is kept as
``native_confidence``: it is the number the original student reported, and the audit
trail should show it.

It exists so the loop is demonstrably closed with nothing installed, and so a real
System-1 model has a number to beat.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .confidence import uniform
from .contracts import DecisionExample, GenerativeAnswer, GenerativeExample, ModelInfo, Question, RawAnswer, State
from .dataset import label_key

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(state: State) -> frozenset[str]:
    text = state if isinstance(state, str) else json.dumps(state, sort_keys=True)
    return frozenset(_TOKEN.findall(text.lower()))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


class NearestNeighbourDecisionModel:
    name = "nearest-neighbour"

    def __init__(self, k: int = 5) -> None:
        if k < 1:
            raise ValueError("k must be at least 1")
        self.k = k
        self._memory: dict[str, list[tuple[frozenset[str], str]]] = {}
        self._examples = 0

    @property
    def info(self) -> ModelInfo:
        return ModelInfo("baseline", self.name, f"examples={self._examples}", "memory")

    @property
    def fitted(self) -> bool:
        return self._examples > 0

    def fit(self, examples: Iterable[DecisionExample]) -> int:
        """Remember every example. Returns how many were remembered."""
        memory: dict[str, list[tuple[frozenset[str], str]]] = {}
        count = 0
        for example in examples:
            memory.setdefault(example.question_name, []).append((tokens(example.state), label_key(example)))
            count += 1
        self._memory, self._examples = memory, count
        return count

    def decide(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, RawAnswer]:
        query = tokens(state)
        out: dict[str, RawAnswer] = {}
        for name, question in questions.items():
            keys = question.keys()
            scored = sorted(
                ((jaccard(query, remembered), key) for remembered, key in self._memory.get(name, ()) if key in keys),
                key=lambda pair: -pair[0],
            )[: self.k]
            best = scored[0][0] if scored else 0.0
            votes = {k: 0.0 for k in keys}
            for similarity, key in scored:
                votes[key] += similarity**3
            total = sum(votes.values())
            if total <= 0.0 or best <= 0.0:
                out[name] = RawAnswer(uniform(keys), 0.0)
                continue
            n = len(keys)
            out[name] = RawAnswer({k: best * (votes[k] / total) + (1.0 - best) / n for k in keys}, best)
        return out


class NearestNeighbourGenerativeModel:
    """The generative baseline: answer with the output of the most similar captured example,
    confidence = that similarity. Exactly the original v0.1 student behind the
    ``GenerativeModel`` port. It copies; it does not extract or compose, which is why it
    is honest about extraction tasks and why the exemplar rung (PX-111) exists."""

    name = "nearest-neighbour-generative"

    def __init__(self) -> None:
        self._memory: list[tuple[frozenset[str], Any]] = []

    @property
    def info(self) -> ModelInfo:
        return ModelInfo("baseline", self.name, f"examples={len(self._memory)}", "memory")

    @property
    def fitted(self) -> bool:
        return bool(self._memory)

    def fit(self, examples: Iterable[GenerativeExample]) -> int:
        self._memory = [(tokens(e.state), e.output) for e in examples]
        return len(self._memory)

    def generate(self, state: State, instructions: str, output_schema: Mapping[str, str]) -> GenerativeAnswer:
        if not self._memory:
            return GenerativeAnswer(None, 0.0)
        query = tokens(state)
        best, best_output = 0.0, None
        for remembered, output in self._memory:
            similarity = jaccard(query, remembered)
            if similarity > best:
                best, best_output = similarity, output
        return GenerativeAnswer(best_output, best)
