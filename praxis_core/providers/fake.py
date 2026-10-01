"""One fake per port. These are the test doubles the whole suite is built on, and the
fixtures for fault injection: each fake can be told to fail, stall, or return garbage,
so the router's guarantees are proven against a hostile adapter rather than assumed.

They are also what ``python -m praxis demo`` runs on, which is why the demo needs no
installs and no keys.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from praxis_core.contracts import (
    Answer,
    DecisionExample,
    Distribution,
    GenerativeAnswer,
    ModelArtifact,
    ModelInfo,
    Question,
    RawAnswer,
    State,
    TeacherAnswer,
    TraceEvent,
    utc_now_iso,
)

#: ``(state, question name, question) -> answer key``: how a fake picks its answer.
Picker = Callable[[State, str, Question], str]
#: ``(state, question name, question) -> typed answer``: how a fake teacher answers.
Oracle = Callable[[State, str, Question], Answer]

MALFORMED_MODES: tuple[str, ...] = (
    "not-a-mapping",
    "missing-question",
    "unknown-key",
    "bad-sum",
    "nan",
    "negative",
    "empty",
    "not-numbers",
)


def peaked(keys: Sequence[str], key: str, peak: float) -> Distribution:
    """``peak`` on one key, the rest shared evenly. ``peak=1.0`` is one-hot."""
    if key not in keys:
        raise ValueError(f"{key!r} is not one of {list(keys)}")
    rest = (1.0 - peak) / (len(keys) - 1) if len(keys) > 1 else 0.0
    return {k: (peak if k == key else rest) for k in keys}


class FakeDecisionModel:
    """A System-1 that answers by a rule, or misbehaves on request.

    ``pick`` chooses the key per question (default: the first key). ``peak`` is the mass
    put on it, one value for every question or a mapping by question name. ``fail`` is
    raised on every call. ``delay_s`` stalls each call, which is how a timeout is injected.
    ``malformed`` selects one of ``MALFORMED_MODES``.
    """

    def __init__(
        self,
        pick: Picker | None = None,
        peak: float | Mapping[str, float] = 0.9,
        *,
        fail: BaseException | None = None,
        delay_s: float = 0.0,
        malformed: str | None = None,
        native_confidence: float | None = None,
        cost_usd: float = 0.0,
        info: ModelInfo | None = None,
    ) -> None:
        if malformed is not None and malformed not in MALFORMED_MODES:
            raise ValueError(f"malformed must be one of {MALFORMED_MODES}")
        self.pick = pick
        self.peak = peak
        self.fail = fail
        self.delay_s = delay_s
        self.malformed = malformed
        self.native_confidence = native_confidence
        self.cost_usd = cost_usd
        self._info = info or ModelInfo("fake", "fake-system1", "0", "raw")
        self.calls = 0

    @property
    def info(self) -> ModelInfo:
        return self._info

    def decide(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, RawAnswer]:
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail is not None:
            raise self.fail
        if self.malformed is not None:
            return self._garbage(questions)  # type: ignore[return-value]
        out: dict[str, RawAnswer] = {}
        for name, question in questions.items():
            keys = question.keys()
            key = self.pick(state, name, question) if self.pick else keys[0]
            peak = self.peak[name] if isinstance(self.peak, Mapping) else self.peak
            out[name] = RawAnswer(
                peaked(keys, key, peak),
                peak if self.native_confidence is None else self.native_confidence,
                self.cost_usd,
            )
        return out

    def _garbage(self, questions: Mapping[str, Question]) -> object:
        mode = self.malformed
        if mode == "not-a-mapping":
            return ["not", "a", "mapping"]
        if mode == "empty":
            return {}
        out: dict[str, Any] = {}
        for name, question in questions.items():
            keys = question.keys()
            if mode == "missing-question":
                continue
            if mode == "unknown-key":
                out[name] = RawAnswer({**peaked(keys, keys[0], 1.0), "smuggled": 0.0})
            elif mode == "bad-sum":
                out[name] = RawAnswer({k: 0.9 for k in keys})
            elif mode == "nan":
                out[name] = RawAnswer({k: float("nan") for k in keys})
            elif mode == "negative":
                d = peaked(keys, keys[0], 1.0)
                d[keys[0]], d[keys[-1]] = 1.5, -0.5
                out[name] = RawAnswer(d)
            elif mode == "not-numbers":
                out[name] = {k: "high" for k in keys}
        return out


class FakeTeacher:
    """A System-2 that answers by an oracle rule, with an optional distribution."""

    def __init__(
        self,
        oracle: Oracle | None = None,
        *,
        fail: BaseException | None = None,
        delay_s: float = 0.0,
        with_distribution: bool = False,
        cost_usd: float = 0.0,
        info: ModelInfo | None = None,
    ) -> None:
        self.oracle = oracle
        self.fail = fail
        self.delay_s = delay_s
        self.with_distribution = with_distribution
        self.cost_usd = cost_usd
        self._info = info or ModelInfo("fake", "fake-teacher", "0")
        self.calls = 0
        self.questions_answered = 0

    @property
    def info(self) -> ModelInfo:
        return self._info

    def answer(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, TeacherAnswer]:
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail is not None:
            raise self.fail
        out: dict[str, TeacherAnswer] = {}
        for name, question in questions.items():
            answer = self.oracle(state, name, question) if self.oracle else self._default(question)
            distribution = None
            if self.with_distribution and question.type != "rank":
                distribution = peaked(question.keys(), question.key_for(answer), 1.0)
            out[name] = TeacherAnswer(answer, distribution, self.cost_usd)
            self.questions_answered += 1
        return out

    @staticmethod
    def _default(question: Question) -> Answer:
        if question.type == "rank":
            return list(question.options)
        return question.answer_for(question.keys()[0])


#: ``(state, instructions, output_schema) -> output``: how a fake generative model answers.
Generator = Callable[[State, str, Mapping[str, str]], Any]

GENERATIVE_MALFORMED_MODES: tuple[str, ...] = (
    "not-an-answer",
    "invalid-output",
    "nan-confidence",
    "confidence-above-one",
    "none-output",
)


class FakeGenerativeModel:
    """A generative student or teacher that answers by a rule, or misbehaves on request.

    ``generate_fn`` produces the output (default: empty strings for every schema field);
    ``confidence`` is what it reports; ``fail``, ``delay_s`` and ``malformed`` inject faults
    exactly as ``FakeDecisionModel`` does.
    """

    def __init__(
        self,
        generate_fn: Generator | None = None,
        confidence: float = 0.9,
        *,
        fail: BaseException | None = None,
        delay_s: float = 0.0,
        malformed: str | None = None,
        cost_usd: float = 0.0,
        info: ModelInfo | None = None,
    ) -> None:
        if malformed is not None and malformed not in GENERATIVE_MALFORMED_MODES:
            raise ValueError(f"malformed must be one of {GENERATIVE_MALFORMED_MODES}")
        self.generate_fn = generate_fn
        self.confidence = confidence
        self.fail = fail
        self.delay_s = delay_s
        self.malformed = malformed
        self.cost_usd = cost_usd
        self._info = info or ModelInfo("fake", "fake-generative", "0")
        self.calls = 0

    @property
    def info(self) -> ModelInfo:
        return self._info

    def generate(self, state: State, instructions: str, output_schema: Mapping[str, str]) -> GenerativeAnswer:
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail is not None:
            raise self.fail
        if self.malformed == "not-an-answer":
            return {"output": "x"}  # type: ignore[return-value]
        if self.malformed == "invalid-output":
            return GenerativeAnswer({"smuggled": 1}, self.confidence)
        if self.malformed == "none-output":
            return GenerativeAnswer(None, self.confidence)
        output = (
            self.generate_fn(state, instructions, output_schema) if self.generate_fn else {k: "" for k in output_schema}
        )
        if self.malformed == "nan-confidence":
            return GenerativeAnswer(output, float("nan"))
        if self.malformed == "confidence-above-one":
            return GenerativeAnswer(output, 1.7)
        return GenerativeAnswer(output, self.confidence, self.cost_usd)


class FakeScalarCalibrator:
    """Identity on a scalar; ``fitted`` controls the flag."""

    def __init__(self, fitted: bool = False, version: str = "fake-scalar-calibrator") -> None:
        self.fitted = fitted
        self._version = version
        self.fit_calls = 0

    @property
    def version(self) -> str:
        return self._version

    def fit(self, traces: Sequence[TraceEvent]) -> Mapping[str, float]:
        self.fit_calls += 1
        self.fitted = True
        return {}

    def apply(self, confidence: float) -> float:
        return float(confidence)

    def is_fitted(self) -> bool:
        return self.fitted


class FakeCalibrator:
    """Identity. ``fitted`` controls whether it claims to have touched the distribution."""

    def __init__(self, fitted: bool = False, version: str = "fake-calibrator") -> None:
        self.fitted = fitted
        self._version = version
        self.fit_calls = 0

    @property
    def version(self) -> str:
        return self._version

    def fit(self, traces: Sequence[TraceEvent]) -> Mapping[str, float]:
        self.fit_calls += 1
        self.fitted = True
        return {}

    def apply(self, question: Question, distribution: Mapping[str, float]) -> Distribution:
        return {str(k): float(v) for k, v in distribution.items()}

    def is_fitted(self, question: Question) -> bool:
        return self.fitted


class FakeTrainer:
    def __init__(self, provider: str = "fake", model: str = "fake-student") -> None:
        self.provider, self.model = provider, model
        self.trained_on: list[int] = []

    def train(self, examples: Sequence[DecisionExample], base: str | None = None) -> ModelArtifact:
        self.trained_on.append(len(examples))
        capability = examples[0].capability if examples else "unknown.unknown"
        return ModelArtifact(
            capability,
            self.model,
            str(len(self.trained_on)),
            self.provider,
            base or self.model,
            "fake",
            "memory://fake",
            {"examples": float(len(examples))},
            utc_now_iso(),
        )


class FakeTraceSink:
    """In memory. ``fail`` is raised from ``record`` to prove the router swallows it."""

    def __init__(self, *, fail: BaseException | None = None) -> None:
        self.traces: list[TraceEvent] = []
        self.fail = fail
        self.record_calls = 0

    def record(self, trace: TraceEvent) -> None:
        self.record_calls += 1
        if self.fail is not None:
            raise self.fail
        self.traces.append(trace)

    def read(self, capability: str | None = None) -> Iterator[TraceEvent]:
        for trace in list(self.traces):
            if capability is None or trace.capability == capability:
                yield trace


class FakeSchemaValidator:
    def __init__(self, verdict: tuple[bool, str] = (True, "")) -> None:
        self.verdict = verdict

    def validate(self, schema: Mapping[str, str], output: object) -> tuple[bool, str]:
        return self.verdict


class FakeRegistry:
    def __init__(self) -> None:
        self._artifacts: dict[str, list[ModelArtifact]] = {}
        self._stages: dict[tuple[str, str], str] = {}

    def register(self, artifact: ModelArtifact) -> None:
        self._artifacts.setdefault(artifact.capability, []).append(artifact)

    def get(self, capability: str, version: str | None = None) -> ModelArtifact | None:
        versions = self._artifacts.get(capability, [])
        if version is None:
            return versions[-1] if versions else None
        for artifact in versions:
            if artifact.version == version:
                return artifact
        return None

    def set_stage(self, capability: str, version: str, stage: str) -> None:
        if self.get(capability, version) is None:
            raise KeyError(f"{capability} has no version {version}")
        self._stages[(capability, version)] = stage

    def manifest(self, capability: str) -> dict[str, Any]:
        return {
            "capability": capability,
            "versions": [
                {**a.to_dict(), "stage": self._stages.get((capability, a.version), "candidate")}
                for a in self._artifacts.get(capability, [])
            ],
        }
