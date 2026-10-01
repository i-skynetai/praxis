"""The confidence router — student first, teacher when the student is unsure.

The router is the only component that decides what the application sees. It answers
three questions in order: is there a student, does it clear the threshold, and if not,
who pays for the fallback.

Every decision is recorded. "The student handled 60% of traffic" is a claim that has to
be checkable, and the ledger is what makes it checkable.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from .seam import Capability


@dataclass
class Decision:
    answered_by: str          #: "student" | "teacher"
    confidence: float
    output: Any
    reason: str = ""


@dataclass
class Router:
    capability: Capability
    student: Any | None = None
    threshold: float = 0.7
    ledger: list[Decision] = field(default_factory=list)

    def ask(self, inputs: dict, teacher: Callable[[dict], Any]) -> Decision:
        if self.student is None:
            return self._record(Decision("teacher", 0.0, teacher(inputs), "no student"))

        out, conf = self.student.predict(inputs)
        if conf < self.threshold:
            return self._record(Decision("teacher", conf, teacher(inputs),
                                         f"confidence {conf} below {self.threshold}"))

        ok, why = self.capability.validate(out)
        if not ok:
            # Confident and malformed is worse than unsure. Fall back and say so.
            return self._record(Decision("teacher", conf, teacher(inputs),
                                         f"student output invalid: {why}"))
        return self._record(Decision("student", conf, out))

    def _record(self, d: Decision) -> Decision:
        self.ledger.append(d)
        return d

    def stats(self) -> dict:
        n = len(self.ledger)
        by_student = sum(1 for d in self.ledger if d.answered_by == "student")
        fallbacks: dict[str, int] = {}
        for d in self.ledger:
            if d.answered_by == "teacher" and d.reason:
                fallbacks[d.reason.split(":")[0]] = fallbacks.get(d.reason.split(":")[0], 0) + 1
        return {"asked": n, "student": by_student, "teacher": n - by_student,
                "deflection": round(by_student / n, 3) if n else 0.0,
                "fallback_reasons": fallbacks}
