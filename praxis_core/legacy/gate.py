"""The quality gate — what is allowed to become training data.

A distillation flywheel is only as good as what it learns from, and the failure is
quiet: a student trained on plausible-looking rubbish is confidently wrong, and nothing
in the pipeline complains. So the gate rejects, records why, and the rejections are
readable.
"""
from __future__ import annotations
from collections import Counter
from .seam import Capability, Trace


class Gate:
    """Four checks, cheapest first."""

    def __init__(self, cap: Capability, max_latency_ms: int = 30_000) -> None:
        self.cap = cap
        self.max_latency_ms = max_latency_ms
        self._seen: set[str] = set()
        self.rejections: Counter = Counter()

    def judge(self, trace: Trace) -> Trace:
        ok, why = self._judge(trace)
        trace.accepted, trace.reason = ok, why
        if not ok:
            self.rejections[why.split(":")[0]] += 1
        return trace

    def _judge(self, trace: Trace) -> tuple[bool, str]:
        if trace.capability != self.cap.name:
            return False, f"wrong capability: {trace.capability}"
        valid, why = self.cap.validate(trace.output)
        if not valid:
            return False, f"schema: {why}"
        if trace.latency_ms > self.max_latency_ms:
            return False, f"slow: {trace.latency_ms}ms over {self.max_latency_ms}ms"
        if trace.key in self._seen:
            return False, "duplicate: the same input was already accepted"
        self._seen.add(trace.key)
        return True, ""

    def report(self) -> dict:
        return {"accepted": len(self._seen), "rejected": sum(self.rejections.values()),
                "by_reason": dict(self.rejections)}
