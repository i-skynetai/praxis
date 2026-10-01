"""Ports: the seven interfaces Praxis is built against (plan §3.3), plus the sibling
``GenerativeModel`` port for capabilities that must generate text.

Each port is a ``typing.Protocol``: an adapter satisfies it by having the right methods,
with no base class to inherit and nothing to register. ``praxis_core.providers.fake`` has one
fake per port, and every real adapter is checked against the same conformance tests.

What each port is for, in one line:

* ``DecisionModel``  System-1. A state and typed questions in, one raw distribution per
  question out. Milliseconds. Never trusted without the router's checks.
* ``GenerativeModel``  The generative sibling: output against a declared schema plus a
  confidence. Kept for the LoRA path; not on the critical path of this redesign.
* ``Teacher``  System-2. Same request in, a typed answer per question out, via whatever
  structured-output mechanism the provider has. Permanent: never removed from the loop.
* ``Calibrator``  Puts every provider's raw distribution on one scale so a threshold means
  the same thing everywhere.
* ``Trainer``  Turns a decision dataset into a model artifact. Rung A (temperature refit)
  to Rung D (LoRA) all sit behind this.
* ``TraceSink``  Persists traces and reads them back. Recording must never raise into
  the caller; the router guarantees that, the sink need not.
* ``SchemaValidator``  Validates generative outputs against a host-declared schema. The
  host's schema crosses as a reference, never as a type.
* ``Registry``  Model versions, their stage, and a manifest per capability.
"""
from __future__ import annotations

from typing import Any, Iterator, Mapping, Protocol, Sequence, runtime_checkable

from .contracts import (
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
)


@runtime_checkable
class DecisionModel(Protocol):
    """System-1: fast, typed, calibrated-or-not; the router decides whether to trust it."""

    @property
    def info(self) -> ModelInfo: ...

    def decide(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, RawAnswer]:
        """One raw distribution per question, keyed by the question's ``keys()``.

        Adapters receive ``rank`` questions already converted to ``choice``. Any
        exception, timeout, or malformed return is handled by the router as an
        abstention; adapters need not defend against their own failure.
        """
        ...


@runtime_checkable
class GenerativeModel(Protocol):
    """The generative student: output against a declared schema, with a confidence."""

    @property
    def info(self) -> ModelInfo: ...

    def generate(self, state: State, instructions: str, output_schema: Mapping[str, str]) -> GenerativeAnswer: ...


@runtime_checkable
class Teacher(Protocol):
    """System-2: the permanent fallback and the source of labels."""

    @property
    def info(self) -> ModelInfo: ...

    def answer(self, state: State, questions: Mapping[str, Question]) -> Mapping[str, TeacherAnswer]:
        """A typed answer per question. A ``rank`` question is answered with the option
        keys best first; every other type with its canonical answer."""
        ...


@runtime_checkable
class Calibrator(Protocol):
    """Maps a raw distribution onto the Praxis scale, per (question type, option count)."""

    @property
    def version(self) -> str:
        """Identifies the fitted parameters; recorded on every trace it touches."""
        ...

    def fit(self, traces: Sequence[TraceEvent]) -> Mapping[str, float]:
        """Fit from traces that carry both a raw System-1 distribution and a System-2
        label. Returns the fitted parameters keyed by ``"<type>/<option count>"``."""
        ...

    def apply(self, question: Question, distribution: Mapping[str, float]) -> Distribution: ...

    def is_fitted(self, question: Question) -> bool: ...


@runtime_checkable
class Trainer(Protocol):
    def train(self, examples: Sequence[DecisionExample], base: str | None = None) -> ModelArtifact: ...


@runtime_checkable
class TraceSink(Protocol):
    def record(self, trace: TraceEvent) -> None: ...

    def read(self, capability: str | None = None) -> Iterator[TraceEvent]: ...


@runtime_checkable
class SchemaValidator(Protocol):
    def validate(self, schema: Mapping[str, str], output: object) -> tuple[bool, str]:
        """``(True, "")`` when the output matches the schema, else ``(False, why)``."""
        ...


@runtime_checkable
class Registry(Protocol):
    def register(self, artifact: ModelArtifact) -> None: ...

    def get(self, capability: str, version: str | None = None) -> ModelArtifact | None:
        """A specific version, or the most recently registered one when ``version`` is None."""
        ...

    def set_stage(self, capability: str, version: str, stage: str) -> None: ...

    def manifest(self, capability: str) -> dict[str, Any]: ...
