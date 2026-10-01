"""Contracts: the types every part of Praxis agrees on. Frozen at Phase 0.

Three families live here.

* The **decision contract**: `Question`, `DecisionRequest`, `DecisionResult`. This is the
  request shape the System-1 decision models converged on (a state plus a map of typed
  questions) with what they lack added on top: one confidence scale for every provider,
  a flag saying whether that confidence passed through a fitted calibrator, and abstain
  as a recorded outcome rather than an error.
* The **capability**: what a host declares once. A capability is either ``decision``
  (answered through the decision contract by a System-1 model with a System-2 fallback)
  or ``generative`` (free text or code against a declared output schema).
* The **trace envelope, version 2**: the complete, replayable record of one call. Three
  layers: a stable Praxis envelope that holds no host types, one opaque host partition
  key, and an opaque payload that Praxis stores but never interprets.

Everything is a plain dataclass with ``to_dict`` / ``from_dict``. A trace written today
is readable by the next version, and nothing here depends on a serialisation library.

Naming decisions taken here (plan §5):

* The yes/no question type is ``boolean``. The vendors' name ``noul`` is accepted as an
  alias on input and never written on output.
* ``rank`` is derived from ``choice``: adapters only ever see the choice form, and the
  router sorts the calibrated distribution. No provider has to support it.
* For a ``score`` question the canonical answer is the zero-based index of the level, and
  distributions are keyed by that index as a string (``"0"``, ``"1"``, ...). For a
  ``boolean`` question the keys are ``"true"`` and ``"false"``. This keeps every
  distribution a ``dict[str, float]`` that survives JSON unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence, cast

ENVELOPE_VERSION = 2

QuestionType = Literal["choice", "score", "boolean", "rank"]
CapabilityKind = Literal["decision", "generative"]
Stage = Literal["shadow", "canary", "serve"]
AnsweredBy = Literal["system1", "system2"]
LabelSource = Literal["system2", "outcome", "human"]
TraceSource = Literal["live", "synthetic", "selfplay"]
TraceMode = Literal["call", "observe"]

QUESTION_TYPES: tuple[str, ...] = ("choice", "score", "boolean", "rank")
QUESTION_TYPE_ALIASES: dict[str, str] = {"noul": "boolean", "bool": "boolean", "yes_no": "boolean"}
CAPABILITY_KINDS: tuple[str, ...] = ("decision", "generative")
STAGES: tuple[str, ...] = ("shadow", "canary", "serve")
ANSWERED_BY: tuple[str, ...] = ("system1", "system2")
LABEL_SOURCES: tuple[str, ...] = ("system2", "outcome", "human")
TRACE_SOURCES: tuple[str, ...] = ("live", "synthetic", "selfplay")
TRACE_MODES: tuple[str, ...] = ("call", "observe")

BOOLEAN_KEYS: tuple[str, str] = ("true", "false")

#: What a question is answered with: an option key, a level index, a truth value, or
#: (for ``rank``) the option keys best first.
Answer = str | int | bool | list[str]
#: What a decision is about. Praxis never interprets it beyond serialising it.
State = str | dict[str, Any]
#: A probability per answer key. Sums to one.
Distribution = dict[str, float]

_CAPABILITY_NAME = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$")


# --------------------------------------------------------------------------- helpers

def stable_hash(value: object) -> str:
    """A short, stable digest of any JSON-serialisable value. Used for definition hashes."""
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def normalise_question_type(value: object) -> QuestionType:
    """Accept the canonical names and the vendor alias ``noul``; reject anything else."""
    if not isinstance(value, str):
        raise ValueError(f"question type must be a string, got {type(value).__name__}")
    name = QUESTION_TYPE_ALIASES.get(value.strip().lower(), value.strip().lower())
    if name not in QUESTION_TYPES:
        raise ValueError(f"unknown question type {value!r}; expected one of {QUESTION_TYPES}")
    return cast(QuestionType, name)


def _literal(value: object, allowed: tuple[str, ...], what: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{what} must be one of {allowed}, got {value!r}")
    return value


def _answer_from_json(value: object) -> Answer:
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, str):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    raise ValueError(f"an answer must be a key, a level index, a bool or a list of keys, got {value!r}")


def _optional_answer(value: object) -> Answer | None:
    return None if value is None else _answer_from_json(value)


def _distribution_from_json(value: object) -> Distribution:
    if not isinstance(value, Mapping):
        raise ValueError(f"a distribution must be a mapping, got {type(value).__name__}")
    return {str(k): float(v) for k, v in value.items()}


def _optional_distribution(value: object) -> Distribution | None:
    return None if value is None else _distribution_from_json(value)


def _state_from_json(value: object) -> State:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(k): v for k, v in value.items()}
    raise ValueError(f"state must be a string or an object, got {type(value).__name__}")


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(cast(float, value))


# ----------------------------------------------------------------------- Question

@dataclass(frozen=True)
class Question:
    """One typed question about a state.

    ``choice`` and ``rank`` take ``options`` (key to description). ``score`` takes ordered
    ``levels`` (descriptions, low to high). ``boolean`` takes only ``instructions``.
    """

    type: QuestionType
    instructions: str
    options: dict[str, str] = field(default_factory=dict)
    levels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        kind = normalise_question_type(self.type)
        object.__setattr__(self, "type", kind)
        object.__setattr__(self, "options", {str(k): str(v) for k, v in dict(self.options).items()})
        object.__setattr__(self, "levels", tuple(str(level) for level in self.levels))
        if not self.instructions or not self.instructions.strip():
            raise ValueError("a question needs instructions")
        if kind in ("choice", "rank"):
            if len(self.options) < 2:
                raise ValueError(f"a {kind} question needs at least two options")
            if any(not key.strip() for key in self.options):
                raise ValueError("option keys must not be empty")
            if self.levels:
                raise ValueError(f"a {kind} question takes options, not levels")
        elif kind == "score":
            if len(self.levels) < 2:
                raise ValueError("a score question needs at least two ordered levels")
            if any(not level.strip() for level in self.levels):
                raise ValueError("every score level needs a description")
            if self.options:
                raise ValueError("a score question takes levels, not options")
        else:
            if self.options or self.levels:
                raise ValueError("a boolean question takes neither options nor levels")

    # constructors --------------------------------------------------------------
    @classmethod
    def choice(cls, instructions: str, options: Mapping[str, str]) -> Question:
        return cls("choice", instructions, dict(options))

    @classmethod
    def score(cls, instructions: str, levels: Sequence[str]) -> Question:
        return cls("score", instructions, levels=tuple(levels))

    @classmethod
    def boolean(cls, instructions: str) -> Question:
        return cls("boolean", instructions)

    @classmethod
    def rank(cls, instructions: str, options: Mapping[str, str]) -> Question:
        return cls("rank", instructions, dict(options))

    # shape ---------------------------------------------------------------------
    def keys(self) -> tuple[str, ...]:
        """The answer keys, in declared order. Every distribution is keyed by these."""
        if self.type in ("choice", "rank"):
            return tuple(self.options)
        if self.type == "score":
            return tuple(str(i) for i in range(len(self.levels)))
        return BOOLEAN_KEYS

    @property
    def option_count(self) -> int:
        return len(self.keys())

    def as_choice(self) -> Question:
        """The form an adapter sees: ``rank`` becomes ``choice``; everything else is itself."""
        if self.type == "rank":
            return Question("choice", self.instructions, dict(self.options))
        return self

    @property
    def definition_hash(self) -> str:
        """Changes when the type, instructions, options or levels change (``options_or_levels_hash``)."""
        return stable_hash(self.to_dict())

    # answers -------------------------------------------------------------------
    def key_for(self, answer: Answer) -> str:
        """The distribution key a typed answer corresponds to. For ``rank``, the top key."""
        if self.type == "boolean":
            if isinstance(answer, bool):
                return "true" if answer else "false"
            if isinstance(answer, str) and answer.lower() in BOOLEAN_KEYS:
                return answer.lower()
            raise ValueError(f"a boolean answer must be True or False, got {answer!r}")
        if self.type == "score":
            if isinstance(answer, bool) or not isinstance(answer, (int, str)):
                raise ValueError(f"a score answer must be a level index, got {answer!r}")
            index = int(answer)
            if not 0 <= index < len(self.levels):
                raise ValueError(f"level index {index} out of range for {len(self.levels)} levels")
            return str(index)
        if self.type == "rank":
            if not isinstance(answer, list) or not answer:
                raise ValueError("a rank answer must be a non-empty list of option keys")
            answer = answer[0]
        if not isinstance(answer, str) or answer not in self.options:
            raise ValueError(f"answer {answer!r} is not one of the declared options {list(self.options)}")
        return answer

    def answer_for(self, key: str) -> Answer:
        """The typed answer a distribution key corresponds to."""
        if key not in self.keys():
            raise ValueError(f"key {key!r} is not one of {self.keys()}")
        if self.type == "boolean":
            return key == "true"
        if self.type == "score":
            return int(key)
        return key

    def is_valid_answer(self, answer: Answer) -> bool:
        if self.type == "rank":
            return (isinstance(answer, list) and sorted(answer) == sorted(self.options)
                    and len(answer) == len(self.options))
        try:
            self.key_for(answer)
        except ValueError:
            return False
        return True

    def describe(self, answer: Answer) -> str:
        """A human-readable form of an answer: the option description, the level text, yes/no."""
        if self.type == "rank" and isinstance(answer, list):
            return " > ".join(answer)
        key = self.key_for(answer)
        if self.type == "score":
            return self.levels[int(key)]
        if self.type == "boolean":
            return "yes" if key == "true" else "no"
        return self.options[key]

    # serialisation -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "instructions": self.instructions,
                "options": dict(self.options), "levels": list(self.levels)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Question:
        options = data.get("options") or {}
        levels = data.get("levels") or []
        return cls(normalise_question_type(data["type"]), str(data["instructions"]),
                   {str(k): str(v) for k, v in dict(options).items()},
                   tuple(str(level) for level in levels))


# --------------------------------------------------------------------- Capability

@dataclass(frozen=True)
class Capability:
    """What a host declares once: a name, a kind, and either questions or an output schema.

    ``name`` is ``"<domain>.<operation>"``. A ``decision`` capability declares its
    questions; a request may present different options or levels for a question (they
    can be dynamic) but must keep the names and types. A ``generative`` capability
    declares ``instructions`` and a dict-of-types ``output_schema``.
    """

    name: str
    kind: CapabilityKind = "decision"
    questions: dict[str, Question] = field(default_factory=dict)
    instructions: str = ""
    output_schema: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not _CAPABILITY_NAME.match(self.name):
            raise ValueError(f"capability name must look like '<domain>.<operation>', got {self.name!r}")
        object.__setattr__(self, "kind", cast(CapabilityKind, _literal(self.kind, CAPABILITY_KINDS, "kind")))
        object.__setattr__(self, "questions", dict(self.questions))
        object.__setattr__(self, "output_schema", {str(k): str(v) for k, v in dict(self.output_schema).items()})
        if self.kind == "decision":
            if not self.questions:
                raise ValueError("a decision capability declares at least one question")
            if any(not isinstance(q, Question) for q in self.questions.values()):
                raise ValueError("every declared question must be a Question")
        else:
            if not self.output_schema:
                raise ValueError("a generative capability declares an output schema")

    @property
    def definition_hash(self) -> str:
        return stable_hash(self.to_dict())

    def request(self, state: State, context: RequestContext | None = None,
                questions: Mapping[str, Question] | None = None) -> DecisionRequest:
        """A request against this capability, with its declared questions unless overridden."""
        return DecisionRequest(self.name, state, dict(questions if questions is not None else self.questions),
                               context or RequestContext())

    def generative_request(self, state: State, context: RequestContext | None = None) -> GenerativeRequest:
        """A request against a generative capability: the state, the declared instructions and schema."""
        return GenerativeRequest(self.name, state, context or RequestContext())

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind,
                "questions": {name: q.to_dict() for name, q in self.questions.items()},
                "instructions": self.instructions, "output_schema": dict(self.output_schema),
                "description": self.description}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Capability:
        questions = {str(name): Question.from_dict(q) for name, q in dict(data.get("questions") or {}).items()}
        return cls(str(data["name"]), cast(CapabilityKind, _literal(data.get("kind", "decision"), CAPABILITY_KINDS, "kind")),
                   questions, str(data.get("instructions", "")),
                   {str(k): str(v) for k, v in dict(data.get("output_schema") or {}).items()},
                   str(data.get("description", "")))


# ------------------------------------------------------------------------ Request

@dataclass(frozen=True)
class Budget:
    max_latency_ms: int | None = None
    max_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"max_latency_ms": self.max_latency_ms, "max_cost_usd": self.max_cost_usd}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Budget:
        ms = data.get("max_latency_ms")
        return cls(None if ms is None else int(ms), _optional_float(data.get("max_cost_usd")))


@dataclass(frozen=True)
class RequestContext:
    """Opaque to Praxis: a host partition key, who is calling, and a budget."""

    host_partition: str | None = None
    caller: str | None = None
    budget: Budget | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"host_partition": self.host_partition, "caller": self.caller,
                "budget": None if self.budget is None else self.budget.to_dict(),
                "extra": dict(self.extra)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RequestContext:
        budget = data.get("budget")
        return cls(_optional_str(data.get("host_partition")), _optional_str(data.get("caller")),
                   None if budget is None else Budget.from_dict(budget), dict(data.get("extra") or {}))


@dataclass(frozen=True)
class DecisionRequest:
    capability: str
    state: State
    questions: dict[str, Question]
    context: RequestContext = field(default_factory=RequestContext)

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", dict(self.questions))
        if not self.questions:
            raise ValueError("a decision request carries at least one question")

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "state": self.state,
                "questions": {name: q.to_dict() for name, q in self.questions.items()},
                "context": self.context.to_dict()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionRequest:
        return cls(str(data["capability"]), _state_from_json(data["state"]),
                   {str(name): Question.from_dict(q) for name, q in dict(data["questions"]).items()},
                   RequestContext.from_dict(data.get("context") or {}))


@dataclass(frozen=True)
class GenerativeRequest:
    """A request against a generative capability. The instructions and the output schema
    come from the capability; the request carries what the decision is about."""

    capability: str
    state: State
    context: RequestContext = field(default_factory=RequestContext)

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "state": self.state, "context": self.context.to_dict()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GenerativeRequest:
        return cls(str(data["capability"]), _state_from_json(data["state"]),
                   RequestContext.from_dict(data.get("context") or {}))


# ------------------------------------------------------------------------- Result

@dataclass(frozen=True)
class ModelInfo:
    """Who answered: provider, model, version, and the provider's own level name."""

    provider: str
    model: str
    version: str = ""
    level: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "version": self.version, "level": self.level}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelInfo:
        return cls(str(data["provider"]), str(data["model"]), str(data.get("version", "")), str(data.get("level", "")))


@dataclass(frozen=True)
class DecisionResult:
    """One answered question. ``confidence`` is on the Praxis scale (one minus normalised
    entropy of the calibrated distribution) whoever answered; ``native_confidence`` is
    what the provider said, kept for audit; ``calibrated`` says whether a fitted
    calibrator touched the distribution; ``abstain`` says the policy sent this question
    to System-2."""

    question: str
    answer: Answer
    distribution: Distribution
    confidence: float
    native_confidence: float | None
    calibrated: bool
    abstain: bool
    answered_by: AnsweredBy
    provider: str
    model: str
    version: str
    level: str
    latency_ms: float
    cost_usd: float
    trace_id: str
    expected_value: float | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"question": self.question, "answer": self.answer, "distribution": dict(self.distribution),
                "confidence": self.confidence, "native_confidence": self.native_confidence,
                "calibrated": self.calibrated, "abstain": self.abstain, "answered_by": self.answered_by,
                "provider": self.provider, "model": self.model, "version": self.version, "level": self.level,
                "latency_ms": self.latency_ms, "cost_usd": self.cost_usd, "trace_id": self.trace_id,
                "expected_value": self.expected_value, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionResult:
        return cls(str(data["question"]), _answer_from_json(data["answer"]),
                   _distribution_from_json(data["distribution"]), float(data["confidence"]),
                   _optional_float(data.get("native_confidence")), bool(data["calibrated"]), bool(data["abstain"]),
                   cast(AnsweredBy, _literal(data["answered_by"], ANSWERED_BY, "answered_by")),
                   str(data["provider"]), str(data["model"]), str(data.get("version", "")), str(data.get("level", "")),
                   float(data["latency_ms"]), float(data.get("cost_usd", 0.0)), str(data["trace_id"]),
                   _optional_float(data.get("expected_value")), str(data.get("reason", "")))


@dataclass(frozen=True)
class GenerativeResult:
    """One answered generative call. The same fields as a DecisionResult where they apply,
    plus ``schema_valid``: whether the served output passed the capability's validator."""

    output: Any
    confidence: float
    native_confidence: float | None
    calibrated: bool
    abstain: bool
    answered_by: AnsweredBy
    provider: str
    model: str
    version: str
    level: str
    latency_ms: float
    cost_usd: float
    trace_id: str
    schema_valid: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"output": self.output, "confidence": self.confidence, "native_confidence": self.native_confidence,
                "calibrated": self.calibrated, "abstain": self.abstain, "answered_by": self.answered_by,
                "provider": self.provider, "model": self.model, "version": self.version, "level": self.level,
                "latency_ms": self.latency_ms, "cost_usd": self.cost_usd, "trace_id": self.trace_id,
                "schema_valid": self.schema_valid, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GenerativeResult:
        return cls(data.get("output"), float(data["confidence"]), _optional_float(data.get("native_confidence")),
                   bool(data["calibrated"]), bool(data["abstain"]),
                   cast(AnsweredBy, _literal(data["answered_by"], ANSWERED_BY, "answered_by")),
                   str(data["provider"]), str(data["model"]), str(data.get("version", "")), str(data.get("level", "")),
                   float(data["latency_ms"]), float(data.get("cost_usd", 0.0)), str(data["trace_id"]),
                   bool(data.get("schema_valid", True)), str(data.get("reason", "")))


# ------------------------------------------------------------- adapter return types

@dataclass(frozen=True)
class RawAnswer:
    """What a System-1 adapter returns per question: the provider's distribution over the
    question's keys, untouched, plus whatever confidence the provider itself reported."""

    distribution: Distribution
    native_confidence: float | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True)
class TeacherAnswer:
    """What a System-2 adapter returns per question: a typed answer, and a distribution
    when the provider exposed one."""

    answer: Answer
    distribution: Distribution | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True)
class GenerativeAnswer:
    """What a generative student returns: an output against the declared schema, and how
    sure it is. The confidence source is the adapter's business; the router validates."""

    output: Any
    confidence: float
    cost_usd: float = 0.0


@dataclass(frozen=True)
class ModelArtifact:
    """What a trainer produces and a registry records."""

    capability: str
    name: str
    version: str
    provider: str
    model: str
    level: str = ""
    uri: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "name": self.name, "version": self.version,
                "provider": self.provider, "model": self.model, "level": self.level, "uri": self.uri,
                "metrics": dict(self.metrics), "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelArtifact:
        return cls(str(data["capability"]), str(data["name"]), str(data["version"]), str(data["provider"]),
                   str(data["model"]), str(data.get("level", "")), str(data.get("uri", "")),
                   {str(k): float(v) for k, v in dict(data.get("metrics") or {}).items()},
                   str(data.get("created_at", "")))


# ------------------------------------------------------------------------ Dataset

@dataclass(frozen=True)
class DecisionExample:
    """One labelled example for a decision student (plan §3.5)."""

    capability: str
    question_name: str
    question_type: QuestionType
    state: State
    options_or_levels: dict[str, Any]
    label: Answer
    label_source: LabelSource = "system2"
    teacher_distribution: Distribution | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "question_name": self.question_name,
                "question_type": self.question_type, "state": self.state,
                "options_or_levels": dict(self.options_or_levels), "label": self.label,
                "label_source": self.label_source, "teacher_distribution": self.teacher_distribution,
                "meta": dict(self.meta)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionExample:
        return cls(str(data["capability"]), str(data["question_name"]), normalise_question_type(data["question_type"]),
                   _state_from_json(data["state"]), dict(data.get("options_or_levels") or {}),
                   _answer_from_json(data["label"]),
                   cast(LabelSource, _literal(data.get("label_source", "system2"), LABEL_SOURCES, "label_source")),
                   _optional_distribution(data.get("teacher_distribution")), dict(data.get("meta") or {}))


@dataclass(frozen=True)
class GenerativeExample:
    """One labelled example for a generative student: a state and the output to learn."""

    capability: str
    state: State
    output: Any
    label_source: LabelSource = "system2"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"capability": self.capability, "state": self.state, "output": self.output,
                "label_source": self.label_source, "meta": dict(self.meta)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GenerativeExample:
        return cls(str(data["capability"]), _state_from_json(data["state"]), data.get("output"),
                   cast(LabelSource, _literal(data.get("label_source", "system2"), LABEL_SOURCES, "label_source")),
                   dict(data.get("meta") or {}))


# ------------------------------------------------------------------ Trace envelope

@dataclass
class GenerationTrace:
    """The generative part of the envelope: both outputs, validity, confidence, and whether
    the two agreed. ``matched`` is None unless both outputs exist."""

    answered_by: AnsweredBy
    abstain: bool
    output: Any = None
    system1_output: Any = None
    system2_output: Any = None
    schema_valid: bool | None = None
    confidence: float | None = None
    native_confidence: float | None = None
    calibrator_version: str | None = None
    matched: bool | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"answered_by": self.answered_by, "abstain": self.abstain, "output": self.output,
                "system1_output": self.system1_output, "system2_output": self.system2_output,
                "schema_valid": self.schema_valid, "confidence": self.confidence,
                "native_confidence": self.native_confidence, "calibrator_version": self.calibrator_version,
                "matched": self.matched, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GenerationTrace:
        matched = data.get("matched")
        valid = data.get("schema_valid")
        return cls(cast(AnsweredBy, _literal(data["answered_by"], ANSWERED_BY, "answered_by")), bool(data["abstain"]),
                   data.get("output"), data.get("system1_output"), data.get("system2_output"),
                   None if valid is None else bool(valid), _optional_float(data.get("confidence")),
                   _optional_float(data.get("native_confidence")), _optional_str(data.get("calibrator_version")),
                   None if matched is None else bool(matched), str(data.get("reason", "")))

@dataclass
class QuestionTrace:
    """The per-question part of the envelope (plan §3.5). ``question`` is the question as
    presented, so a trace is replayable even when options were dynamic."""

    name: str
    question_type: QuestionType
    options_or_levels_hash: str
    question: Question
    answered_by: AnsweredBy
    abstain: bool
    answer: Answer | None = None
    system1_answer: Answer | None = None
    system2_answer: Answer | None = None
    raw_distribution: Distribution | None = None
    calibrated_distribution: Distribution | None = None
    confidence: float | None = None
    native_confidence: float | None = None
    calibrator_version: str | None = None
    system2_distribution: Distribution | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "question_type": self.question_type,
                "options_or_levels_hash": self.options_or_levels_hash, "question": self.question.to_dict(),
                "answered_by": self.answered_by, "abstain": self.abstain, "answer": self.answer,
                "system1_answer": self.system1_answer, "system2_answer": self.system2_answer,
                "raw_distribution": self.raw_distribution, "calibrated_distribution": self.calibrated_distribution,
                "confidence": self.confidence, "native_confidence": self.native_confidence,
                "calibrator_version": self.calibrator_version, "system2_distribution": self.system2_distribution,
                "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QuestionTrace:
        return cls(str(data["name"]), normalise_question_type(data["question_type"]),
                   str(data["options_or_levels_hash"]), Question.from_dict(data["question"]),
                   cast(AnsweredBy, _literal(data["answered_by"], ANSWERED_BY, "answered_by")), bool(data["abstain"]),
                   _optional_answer(data.get("answer")), _optional_answer(data.get("system1_answer")),
                   _optional_answer(data.get("system2_answer")), _optional_distribution(data.get("raw_distribution")),
                   _optional_distribution(data.get("calibrated_distribution")), _optional_float(data.get("confidence")),
                   _optional_float(data.get("native_confidence")), _optional_str(data.get("calibrator_version")),
                   _optional_distribution(data.get("system2_distribution")), str(data.get("reason", "")))


@dataclass
class TraceEvent:
    """The complete, replayable record of one call. Envelope version 2.

    Layer one, the Praxis envelope, is every field down to ``host_partition``: stable
    across hosts, holds no host type. Layer two is ``host_partition``, the host's own
    isolation key, opaque. Layer three is the payload: ``state`` and the late-bound
    ``outcome`` and ``feedback`` blobs, which Praxis stores and never interprets.
    """

    trace_id: str
    capability: str
    capability_kind: CapabilityKind
    capability_hash: str
    stage: Stage
    answered_by: AnsweredBy
    abstain: bool
    questions: list[QuestionTrace]
    state: State
    envelope_version: int = ENVELOPE_VERSION
    parent_trace_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    reason: str = ""
    system1: ModelInfo | None = None
    system2: ModelInfo | None = None
    system1_latency_ms: float | None = None
    system2_latency_ms: float | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    system1_error: str | None = None
    success: bool = True
    error_message: str | None = None
    source: TraceSource = "live"
    mode: TraceMode = "call"
    label_candidate: bool = False
    teacher_distillable: bool = True
    dataset_version: str | None = None
    pii_redacted: bool = False
    schema_valid: bool | None = None
    generation: GenerationTrace | None = None
    host_partition: str | None = None
    caller: str | None = None
    outcome: dict[str, Any] | None = None
    feedback: dict[str, Any] | None = None

    @property
    def input_key(self) -> str:
        """Capability plus state, hashed. Two traces with the same key saw the same input."""
        return stable_hash({"c": self.capability, "s": self.state})

    def question(self, name: str) -> QuestionTrace:
        for q in self.questions:
            if q.name == name:
                return q
        raise KeyError(name)

    def to_request(self) -> DecisionRequest | GenerativeRequest:
        """Rebuild the request this trace recorded: the replay-equivalence property.
        The state, every question as presented, and the host partition and caller are
        carried; a budget and the opaque ``extra`` are not part of what a model saw."""
        context = RequestContext(host_partition=self.host_partition, caller=self.caller)
        if self.capability_kind == "generative":
            return GenerativeRequest(self.capability, self.state, context)
        return DecisionRequest(self.capability, self.state, {q.name: q.question for q in self.questions}, context)

    def to_dict(self) -> dict[str, Any]:
        return {"envelope_version": self.envelope_version, "trace_id": self.trace_id,
                "parent_trace_id": self.parent_trace_id, "created_at": self.created_at,
                "capability": self.capability, "capability_kind": self.capability_kind,
                "capability_hash": self.capability_hash, "stage": self.stage,
                "answered_by": self.answered_by, "abstain": self.abstain, "reason": self.reason,
                "system1": None if self.system1 is None else self.system1.to_dict(),
                "system2": None if self.system2 is None else self.system2.to_dict(),
                "system1_latency_ms": self.system1_latency_ms, "system2_latency_ms": self.system2_latency_ms,
                "latency_ms": self.latency_ms, "cost_usd": self.cost_usd,
                "system1_error": self.system1_error, "success": self.success, "error_message": self.error_message,
                "source": self.source, "mode": self.mode, "label_candidate": self.label_candidate,
                "teacher_distillable": self.teacher_distillable, "dataset_version": self.dataset_version,
                "pii_redacted": self.pii_redacted, "schema_valid": self.schema_valid,
                "generation": None if self.generation is None else self.generation.to_dict(),
                "questions": [q.to_dict() for q in self.questions],
                "host_partition": self.host_partition, "caller": self.caller,
                "state": self.state, "outcome": self.outcome, "feedback": self.feedback}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TraceEvent:
        version = int(data.get("envelope_version", ENVELOPE_VERSION))
        if version != ENVELOPE_VERSION:
            raise ValueError(f"trace envelope version {version} is not readable by this Praxis (wants {ENVELOPE_VERSION})")
        system1, system2 = data.get("system1"), data.get("system2")
        outcome, feedback = data.get("outcome"), data.get("feedback")
        generation = data.get("generation")
        return cls(
            trace_id=str(data["trace_id"]), capability=str(data["capability"]),
            capability_kind=cast(CapabilityKind, _literal(data["capability_kind"], CAPABILITY_KINDS, "capability_kind")),
            capability_hash=str(data["capability_hash"]),
            stage=cast(Stage, _literal(data["stage"], STAGES, "stage")),
            answered_by=cast(AnsweredBy, _literal(data["answered_by"], ANSWERED_BY, "answered_by")),
            abstain=bool(data["abstain"]),
            questions=[QuestionTrace.from_dict(q) for q in list(data.get("questions") or [])],
            state=_state_from_json(data["state"]), envelope_version=version,
            parent_trace_id=_optional_str(data.get("parent_trace_id")), created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
            system1=None if system1 is None else ModelInfo.from_dict(system1),
            system2=None if system2 is None else ModelInfo.from_dict(system2),
            system1_latency_ms=_optional_float(data.get("system1_latency_ms")),
            system2_latency_ms=_optional_float(data.get("system2_latency_ms")),
            latency_ms=float(data.get("latency_ms", 0.0)), cost_usd=float(data.get("cost_usd", 0.0)),
            system1_error=_optional_str(data.get("system1_error")), success=bool(data.get("success", True)),
            error_message=_optional_str(data.get("error_message")),
            source=cast(TraceSource, _literal(data.get("source", "live"), TRACE_SOURCES, "source")),
            mode=cast(TraceMode, _literal(data.get("mode", "call"), TRACE_MODES, "mode")),
            label_candidate=bool(data.get("label_candidate", False)),
            teacher_distillable=bool(data.get("teacher_distillable", True)),
            dataset_version=_optional_str(data.get("dataset_version")),
            pii_redacted=bool(data.get("pii_redacted", False)),
            schema_valid=None if data.get("schema_valid") is None else bool(data["schema_valid"]),
            generation=None if generation is None else GenerationTrace.from_dict(generation),
            host_partition=_optional_str(data.get("host_partition")), caller=_optional_str(data.get("caller")),
            outcome=None if outcome is None else dict(outcome), feedback=None if feedback is None else dict(feedback))

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> TraceEvent:
        return cls.from_dict(json.loads(text))


def is_finite(value: object) -> bool:
    """True for a real, finite number (bools excluded)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalise_output(value: Any) -> Any:
    """The default notion of "the same output": strings stripped and case-folded, numbers as
    they are, mappings compared as mappings, lists in order. Hosts with a looser notion
    pass their own match function to the generative router."""
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    if isinstance(value, Mapping):
        return {str(k): normalise_output(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalise_output(v) for v in value]
    return value


def outputs_match(a: Any, b: Any) -> bool:
    return bool(normalise_output(a) == normalise_output(b))
