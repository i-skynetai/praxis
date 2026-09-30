"""The seam — the one place a capability meets a model.

A capability declares what it takes and what it returns. Everything Praxis does hangs
off that declaration: capture knows the shape of a trace, the gate knows what a valid
output looks like, the router knows what the student must produce.

This is deliberately **not** an HTTP proxy in front of a provider. Mirroring a gateway
was considered and rejected (ADR-002): a proxy sees bytes, so it cannot tell a good
answer from a badly-formed one, cannot judge confidence, and forces every application
through a network hop it did not ask for. The seam sits inside the application, where
the types still exist.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
import json, time, hashlib
from .core.validate import DictOfTypesValidator


@dataclass(frozen=True)
class Capability:
    """One narrow job a model does, declared in types."""
    name: str
    instruction: str
    output_schema: dict                      #: {field: "str"|"int"|"float"|"bool"|"list"}
    examples: list[dict] = field(default_factory=list)

    def validate(self, output: Any) -> tuple[bool, str]:
        """Is this output the shape the capability promised?

        Delegates to the shared dict-of-types validator (``praxis.core.validate``), which
        sits behind the ``SchemaValidator`` port so other validators can replace it.
        """
        return DictOfTypesValidator().validate(self.output_schema, output)


@dataclass
class Trace:
    """One teacher call, recorded. This is the training data."""
    capability: str
    inputs: dict
    output: Any
    model: str
    latency_ms: int
    cost_usd: float = 0.0
    accepted: bool | None = None            #: set by the gate
    reason: str = ""

    @property
    def key(self) -> str:
        blob = json.dumps({"c": self.capability, "i": self.inputs}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def to_json(self) -> str:
        d = dict(self.__dict__); d["key"] = self.key
        return json.dumps(d, sort_keys=True)


def call_teacher(cap: Capability, inputs: dict, model_fn: Callable[[str], Any],
                 model_name: str = "teacher") -> Trace:
    """Run the expensive model through the seam, and record what happened."""
    prompt = f"{cap.instruction}\n\nInput: {json.dumps(inputs, sort_keys=True)}\n"
    started = time.time()
    raw = model_fn(prompt)
    return Trace(capability=cap.name, inputs=inputs, output=raw, model=model_name,
                 latency_ms=int((time.time() - started) * 1000))
