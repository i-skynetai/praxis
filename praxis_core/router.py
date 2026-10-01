"""The router: System-1 first, System-2 when the policy says so, and a trace either way.

Per call, in order (plan §3.4):

1. Resolve the policy: threshold, stage (``shadow`` | ``canary`` | ``serve``), canary
   share, timeout.
2. Call the System-1 adapter, timed and bounded by the timeout.
3. Pass each raw distribution through the calibrator; compute Praxis confidence.
4. Validate: keys match the question, probabilities sum to one, the answer is declared.
5. In ``serve`` (or ``canary`` when this call is in the share), every question that is
   valid and at or above the threshold is served by System-1.
6. Every other question is an **abstention**: recorded as such, sent to the teacher with
   the same state, served from the teacher's answer, and marked as a candidate label.
7. In ``shadow`` the teacher answers everything, and steps 2 to 4 still run so the trace
   holds both answers side by side.
8. Record the trace. Nothing on that path can raise into the caller.

Two guarantees fall out of this. A System-1 error, timeout or malformed answer is an
abstention with a reason, never a caller-visible failure. And the trace path is
fire-and-forget: a broken sink is counted, not raised.

**Observe mode** (``observe()``) is the other way in, and the one the original design
calls the wedge: the app keeps calling its own model and hands Praxis the answer. Praxis
validates it, runs the configured student in shadow, records the trace with the app's
answer as System-2, and returns the trace. It never raises, whatever it is given: a bad
request or an invalid answer becomes a recorded failure, and anything unexpected is
counted. The app's request path cannot be affected by capture.

The teacher is the one thing that can fail the call. It is the caller's own System-2,
there is nothing behind it, and hiding its failure would mean inventing an answer. The
trace is recorded first, then ``TeacherError`` is raised.

Decisions taken here that the plan left open:

* Routing is **per question**. A request with three questions may serve two from
  System-1 and send one to the teacher; the teacher is then asked only that one.
* A ``rank`` question reaches System-1 as its ``choice`` form and the ranked answer is
  the calibrated distribution sorted. The teacher sees the ``rank`` question itself.
* A System-2 answer without a provider distribution is recorded as one-hot, so its
  Praxis confidence is 1.0 and ``calibrated`` is False. ``answered_by`` is the field to
  filter on, not confidence.
"""
from __future__ import annotations

import random
import threading
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping

from .confidence import argmax, check_distribution, confidence, expected_value, one_hot, rank, uniform
from .contracts import (
    Answer,
    Capability,
    DecisionRequest,
    DecisionResult,
    Distribution,
    ModelInfo,
    Question,
    QuestionTrace,
    RawAnswer,
    Stage,
    TeacherAnswer,
    TraceEvent,
    TraceSource,
    new_trace_id,
)
from .ports import Calibrator, DecisionModel, Teacher, TraceSink


class TeacherError(RuntimeError):
    """The System-2 call failed or answered outside the declared set. The trace was recorded."""


@dataclass(frozen=True)
class RoutingPolicy:
    threshold: float = 0.7
    stage: Stage = "serve"
    canary_share: float = 0.1
    system1_timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        if self.stage not in ("shadow", "canary", "serve"):
            raise ValueError(f"stage must be shadow, canary or serve, got {self.stage!r}")
        if not 0.0 <= self.canary_share <= 1.0:
            raise ValueError("canary_share must be within [0, 1]")
        if self.system1_timeout_ms <= 0:
            raise ValueError("system1_timeout_ms must be positive")


@dataclass
class _Assessed:
    """Steps 2 to 4 for one question."""

    question: Question
    valid: bool
    reason: str = ""
    raw: Distribution | None = None
    calibrated: Distribution | None = None
    confidence: float | None = None
    native_confidence: float | None = None
    was_calibrated: bool = False
    answer: Answer | None = None
    cost_usd: float = 0.0


@dataclass
class _System1Call:
    answers: Mapping[str, RawAnswer] | None = None
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class RouterStats:
    calls: int = 0
    questions: int = 0
    system1_questions: int = 0
    system2_questions: int = 0
    abstain_reasons: Counter[str] = field(default_factory=Counter)
    shadow_compared: int = 0
    shadow_agreed: int = 0
    teacher_failures: int = 0
    trace_failures: int = 0
    observed: int = 0
    observe_failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        share = self.system1_questions / self.questions if self.questions else 0.0
        agreement = self.shadow_agreed / self.shadow_compared if self.shadow_compared else None
        return {"calls": self.calls, "questions": self.questions,
                "system1_questions": self.system1_questions, "system2_questions": self.system2_questions,
                "system1_share": round(share, 4), "abstain_reasons": dict(self.abstain_reasons),
                "shadow_compared": self.shadow_compared, "shadow_agreed": self.shadow_agreed,
                "shadow_agreement": None if agreement is None else round(agreement, 4),
                "teacher_failures": self.teacher_failures, "trace_failures": self.trace_failures,
                "observed": self.observed, "observe_failures": self.observe_failures}


def _call_with_timeout(fn: Callable[[], Mapping[str, RawAnswer]], timeout_s: float) -> _System1Call:
    """Run ``fn`` on a daemon thread and wait at most ``timeout_s``. A stalled adapter is
    left to finish on its own; the caller has already moved on."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - the whole point is to contain it
            box["error"] = exc

    started = time.perf_counter()
    worker = threading.Thread(target=run, name="praxis-system1", daemon=True)
    worker.start()
    worker.join(timeout_s)
    latency = (time.perf_counter() - started) * 1000.0
    if worker.is_alive():
        return _System1Call(None, f"timeout: system1 exceeded {int(timeout_s * 1000)}ms", latency)
    if "error" in box:
        exc = box["error"]
        return _System1Call(None, f"error: {type(exc).__name__}: {exc}", latency)
    return _System1Call(box.get("value"), None, latency)


class DecisionRouter:
    """One router per decision capability."""

    def __init__(self, capability: Capability, teacher: Teacher, system1: DecisionModel | None = None,
                 calibrator: Calibrator | None = None, sink: TraceSink | None = None,
                 policy: RoutingPolicy | None = None, *, rng: random.Random | None = None,
                 source: TraceSource = "live", on_trace_error: Callable[[BaseException], None] | None = None) -> None:
        if capability.kind != "decision":
            raise ValueError(
                f"{capability.name} is a generative capability; the decision router serves decision "
                "capabilities only. The generative path (GenerativeModel) is a later milestone.")
        self.capability = capability
        self.teacher = teacher
        self.system1 = system1
        self.calibrator = calibrator
        self.sink = sink
        self._policy = policy or RoutingPolicy()
        self._rng = rng or random.Random()
        self.source: TraceSource = source
        self.on_trace_error = on_trace_error
        self.stats = RouterStats()

    # policy ------------------------------------------------------------------
    @property
    def policy(self) -> RoutingPolicy:
        return self._policy

    def set_policy(self, policy: RoutingPolicy) -> None:
        self._policy = policy

    def set_stage(self, stage: Stage, **changes: Any) -> None:
        self._policy = replace(self._policy, stage=stage, **changes)

    # entry points ------------------------------------------------------------
    def decide_state(self, state: str | dict[str, Any], context: Any = None) -> dict[str, DecisionResult]:
        """Convenience: a request with the capability's declared questions."""
        return self.decide(self.capability.request(state, context))

    def observe_state(self, state: str | dict[str, Any], answers: Mapping[str, Answer], info: ModelInfo,
                      latency_ms: float = 0.0, cost_usd: float = 0.0, context: Any = None, *,
                      distributions: Mapping[str, Mapping[str, float]] | None = None) -> TraceEvent | None:
        """Convenience: observe with the capability's declared questions."""
        return self.observe(self.capability.request(state, context), answers, info, latency_ms, cost_usd,
                            distributions=distributions)

    def observe(self, request: DecisionRequest, answers: Mapping[str, Answer], info: ModelInfo,
                latency_ms: float = 0.0, cost_usd: float = 0.0, *,
                distributions: Mapping[str, Mapping[str, float]] | None = None) -> TraceEvent | None:
        """The app made the System-2 call itself; hand Praxis the answer. Never raises.

        Returns the recorded trace (``success`` is False when the request or the answer
        was invalid, and then nothing becomes a label), or None if even recording failed.
        """
        try:
            return self._observe(request, answers, info, latency_ms, cost_usd, distributions or {})
        except Exception as exc:  # noqa: BLE001 - capture must never reach the caller
            self.stats.observe_failures += 1
            if self.on_trace_error is not None:
                try:
                    self.on_trace_error(exc)
                except Exception:  # noqa: BLE001
                    pass
            return None

    def _observe(self, request: DecisionRequest, answers: Mapping[str, Answer], info: ModelInfo,
                 latency_ms: float, cost_usd: float, distributions: Mapping[str, Mapping[str, float]]) -> TraceEvent:
        started = time.perf_counter()
        trace_id = new_trace_id()
        policy = self._policy
        try:
            self._check_request(request)
        except ValueError as exc:
            trace = TraceEvent(
                trace_id=trace_id, capability=self.capability.name, capability_kind=self.capability.kind,
                capability_hash=self.capability.definition_hash, stage=policy.stage, answered_by="system2",
                abstain=False, questions=[], state=request.state, reason=f"observe: {exc}", system2=info,
                system2_latency_ms=latency_ms, latency_ms=latency_ms, cost_usd=cost_usd, success=False,
                error_message=f"observe: {exc}", source=self.source, mode="observe", label_candidate=False,
                host_partition=request.context.host_partition, caller=request.context.caller)
            self._record(trace)
            self._count(trace)
            return trace
        system1_call = self._call_system1(request, policy.system1_timeout_ms)       # shadow, if configured
        assessed = {name: self._assess(name, q, system1_call) for name, q in request.questions.items()}
        given: dict[str, TeacherAnswer] = {}
        for name in request.questions:
            if name in answers:
                dist = distributions.get(name)
                given[name] = TeacherAnswer(answers[name], None if dist is None else dict(dist), 0.0)
        error = self._check_teacher_answers(request.questions, given)
        teacher_answers: Mapping[str, TeacherAnswer] = {} if error else given
        results, question_traces = self._assemble(request, assessed, set(), request.questions, teacher_answers,
                                                  system1_call, latency_ms, trace_id, policy, observe=True)
        trace = TraceEvent(
            trace_id=trace_id, capability=self.capability.name, capability_kind=self.capability.kind,
            capability_hash=self.capability.definition_hash, stage=policy.stage, answered_by="system2",
            abstain=False, questions=question_traces, state=request.state,
            reason=error or system1_call.error or "", system1=None if self.system1 is None else self.system1.info,
            system2=info, system1_latency_ms=None if self.system1 is None else system1_call.latency_ms,
            system2_latency_ms=latency_ms, latency_ms=latency_ms + (time.perf_counter() - started) * 1000.0,
            cost_usd=cost_usd, system1_error=system1_call.error, success=error is None,
            error_message=f"observe: {error}" if error else None, source=self.source, mode="observe",
            label_candidate=error is None, host_partition=request.context.host_partition,
            caller=request.context.caller)
        self._record(trace)
        self._count(trace)
        return trace

    def decide(self, request: DecisionRequest) -> dict[str, DecisionResult]:
        started = time.perf_counter()
        self._check_request(request)
        policy = self._policy                                              # step 1
        trace_id = new_trace_id()
        timeout_ms = policy.system1_timeout_ms
        budget = request.context.budget
        if budget is not None and budget.max_latency_ms is not None:
            timeout_ms = min(timeout_ms, budget.max_latency_ms)

        system1_call = self._call_system1(request, timeout_ms)           # step 2
        assessed = {name: self._assess(name, q, system1_call)              # steps 3 and 4
                    for name, q in request.questions.items()}

        in_share = policy.stage == "serve" or (policy.stage == "canary" and self._rng.random() < policy.canary_share)
        served_by_system1: set[str] = set()
        if policy.stage != "shadow":                                        # step 5
            served_by_system1 = {name for name, a in assessed.items()
                                 if in_share and a.valid and a.confidence is not None and a.confidence >= policy.threshold}
        for name, a in assessed.items():
            if name not in served_by_system1 and a.valid and policy.stage != "shadow":
                if not in_share:
                    a.reason = "canary: call outside the System-1 share"
                else:
                    a.reason = f"below threshold: confidence {a.confidence:.3f} < {policy.threshold}"

        to_teacher = ({name: q for name, q in request.questions.items()}      # steps 6 and 7
                      if policy.stage == "shadow"
                      else {name: q for name, q in request.questions.items() if name not in served_by_system1})
        teacher_answers: Mapping[str, TeacherAnswer] = {}
        teacher_latency_ms = 0.0
        teacher_error: str | None = None
        if to_teacher:
            teacher_started = time.perf_counter()
            try:
                teacher_answers = self.teacher.answer(request.state, to_teacher)
                teacher_error = self._check_teacher_answers(to_teacher, teacher_answers)
            except Exception as exc:  # noqa: BLE001 - recorded, then re-raised as TeacherError
                teacher_error = f"teacher error: {type(exc).__name__}: {exc}"
            teacher_latency_ms = (time.perf_counter() - teacher_started) * 1000.0
            if teacher_error is not None:
                teacher_answers = {}          # nothing from a failed teacher is served or recorded as a label

        results, question_traces = self._assemble(request, assessed, served_by_system1, to_teacher, teacher_answers,
                                                  system1_call, teacher_latency_ms, trace_id, policy)
        total_ms = (time.perf_counter() - started) * 1000.0
        trace = TraceEvent(
            trace_id=trace_id, capability=self.capability.name, capability_kind=self.capability.kind,
            capability_hash=self.capability.definition_hash, stage=policy.stage,
            answered_by="system1" if not to_teacher else "system2",
            abstain=any(q.abstain for q in question_traces), questions=question_traces, state=request.state,
            reason=teacher_error or system1_call.error or "",
            system1=None if self.system1 is None else self.system1.info, system2=self.teacher.info,
            system1_latency_ms=None if self.system1 is None else system1_call.latency_ms,
            system2_latency_ms=teacher_latency_ms if to_teacher else None, latency_ms=total_ms,
            cost_usd=sum(r.cost_usd for r in results.values()) if results else 0.0,
            system1_error=system1_call.error, success=teacher_error is None, error_message=teacher_error,
            source=self.source, label_candidate=bool(to_teacher) and teacher_error is None,
            host_partition=request.context.host_partition, caller=request.context.caller)
        self._record(trace)                                                 # step 8
        self._count(trace)
        if teacher_error is not None:
            self.stats.teacher_failures += 1
            raise TeacherError(teacher_error)
        return results

    # steps -------------------------------------------------------------------
    def _check_request(self, request: DecisionRequest) -> None:
        if request.capability != self.capability.name:
            raise ValueError(f"request is for {request.capability!r}; this router serves {self.capability.name!r}")
        declared = self.capability.questions
        if set(request.questions) != set(declared):
            raise ValueError(f"request questions {sorted(request.questions)} do not match the declared "
                             f"{sorted(declared)}")
        for name, q in request.questions.items():
            if q.type != declared[name].type:
                raise ValueError(f"question {name!r} is declared as {declared[name].type}, request says {q.type}")

    def _call_system1(self, request: DecisionRequest, timeout_ms: int) -> _System1Call:
        if self.system1 is None:
            return _System1Call(None, "no system1 model configured", 0.0)
        model = self.system1
        as_choice = {name: q.as_choice() for name, q in request.questions.items()}
        return _call_with_timeout(lambda: model.decide(request.state, as_choice), timeout_ms / 1000.0)

    def _assess(self, name: str, question: Question, call: _System1Call) -> _Assessed:
        if call.error is not None:
            return _Assessed(question, False, call.error)
        try:
            answers = call.answers
            if not isinstance(answers, Mapping):
                return _Assessed(question, False, f"malformed: system1 returned {type(answers).__name__}, not a mapping")
            raw_answer = answers.get(name)
            if raw_answer is None:
                return _Assessed(question, False, f"malformed: system1 returned no answer for {name!r}")
            distribution = getattr(raw_answer, "distribution", None)
            native = getattr(raw_answer, "native_confidence", None)
            cost = getattr(raw_answer, "cost_usd", 0.0)
            keys = question.keys()
            ok, why = check_distribution(distribution, keys)
            if not ok:
                return _Assessed(question, False, f"malformed: {why}")
            assert isinstance(distribution, Mapping)
            raw: Distribution = {k: float(distribution[k]) for k in keys}
            calibrated, was_calibrated = raw, False
            if self.calibrator is not None:
                calibrated = self.calibrator.apply(question.as_choice(), raw)
                ok, why = check_distribution(calibrated, keys)
                if not ok:
                    return _Assessed(question, False, f"calibrator: {why}", raw=raw, native_confidence=native)
                calibrated = {k: float(calibrated[k]) for k in keys}
                was_calibrated = self.calibrator.is_fitted(question.as_choice())
            answer: Answer = rank(calibrated, keys) if question.type == "rank" else question.answer_for(argmax(calibrated, keys))
            if not question.is_valid_answer(answer):
                return _Assessed(question, False, f"malformed: answer {answer!r} is not declared", raw=raw)
            native_conf = float(native) if isinstance(native, (int, float)) and not isinstance(native, bool) else None
            return _Assessed(question, True, "", raw, calibrated, confidence(calibrated), native_conf, was_calibrated,
                             answer, float(cost) if isinstance(cost, (int, float)) else 0.0)
        except Exception as exc:  # noqa: BLE001 - anything an adapter can do wrong ends here
            return _Assessed(question, False, f"malformed: {type(exc).__name__}: {exc}")

    @staticmethod
    def _check_teacher_answers(questions: Mapping[str, Question], answers: object) -> str | None:
        if not isinstance(answers, Mapping):
            return f"teacher error: returned {type(answers).__name__}, not a mapping"
        for name, question in questions.items():
            given = answers.get(name)
            if given is None:
                return f"teacher error: no answer for {name!r}"
            answer = getattr(given, "answer", None)
            if answer is None or not question.is_valid_answer(answer):
                return f"teacher error: answer {answer!r} for {name!r} is not in the declared set"
            distribution = getattr(given, "distribution", None)
            if distribution is not None:
                ok, why = check_distribution(distribution, question.as_choice().keys())
                if not ok:
                    return f"teacher error: distribution for {name!r}: {why}"
        return None

    def _assemble(self, request: DecisionRequest, assessed: Mapping[str, _Assessed], served_by_system1: set[str],
                  to_teacher: Mapping[str, Question], teacher_answers: Mapping[str, TeacherAnswer],
                  system1_call: _System1Call, teacher_latency_ms: float, trace_id: str, policy: RoutingPolicy,
                  observe: bool = False) -> tuple[dict[str, DecisionResult], list[QuestionTrace]]:
        results: dict[str, DecisionResult] = {}
        traces: list[QuestionTrace] = []
        s1_info = self.system1.info if self.system1 is not None else ModelInfo("none", "none")
        s2_info = self.teacher.info
        calibrator_version = self.calibrator.version if self.calibrator is not None else None
        for name, question in request.questions.items():
            a = assessed[name]
            keys = question.keys()
            by_system1 = name in served_by_system1
            teacher_answer = teacher_answers.get(name) if name in to_teacher else None
            system2_answer: Answer | None = teacher_answer.answer if teacher_answer is not None else None
            system2_distribution: Distribution | None = None
            if teacher_answer is not None:
                if teacher_answer.distribution is not None:
                    system2_distribution = {k: float(teacher_answer.distribution[k]) for k in keys}
                else:
                    system2_distribution = one_hot(keys, question.key_for(teacher_answer.answer))
            abstain = not by_system1 and policy.stage != "shadow" and not observe
            if by_system1:
                reason = ""
            elif observe:
                reason = "observe: the app's model served; system1 recorded in shadow"
            elif policy.stage == "shadow":
                reason = "shadow: teacher serves; system1 recorded"
            else:
                reason = a.reason
            traces.append(QuestionTrace(
                name=name, question_type=question.type, options_or_levels_hash=question.definition_hash,
                question=question, answered_by="system1" if by_system1 else "system2", abstain=abstain,
                answer=a.answer if by_system1 else system2_answer, system1_answer=a.answer,
                system2_answer=system2_answer, raw_distribution=a.raw, calibrated_distribution=a.calibrated,
                confidence=a.confidence, native_confidence=a.native_confidence,
                calibrator_version=calibrator_version if a.was_calibrated else None,
                system2_distribution=system2_distribution, reason=reason or a.reason))
            if by_system1:
                assert a.answer is not None and a.calibrated is not None and a.confidence is not None
                results[name] = DecisionResult(
                    name, a.answer, a.calibrated, a.confidence, a.native_confidence, a.was_calibrated, False,
                    "system1", s1_info.provider, s1_info.model, s1_info.version, s1_info.level,
                    system1_call.latency_ms, a.cost_usd, trace_id,
                    expected_value(a.calibrated, keys) if question.type == "score" else None)
            elif teacher_answer is not None and system2_answer is not None and system2_distribution is not None:
                results[name] = DecisionResult(
                    name, system2_answer, system2_distribution, confidence(system2_distribution), None, False, abstain,
                    "system2", s2_info.provider, s2_info.model, s2_info.version, s2_info.level,
                    teacher_latency_ms, teacher_answer.cost_usd, trace_id,
                    expected_value(system2_distribution, keys) if question.type == "score" else None, reason or a.reason)
        return results, traces

    def _record(self, trace: TraceEvent) -> None:
        if self.sink is None:
            return
        try:
            self.sink.record(trace)
        except Exception as exc:  # noqa: BLE001 - step 8: never into the caller
            self.stats.trace_failures += 1
            if self.on_trace_error is not None:
                try:
                    self.on_trace_error(exc)
                except Exception:  # noqa: BLE001
                    pass

    def _count(self, trace: TraceEvent) -> None:
        s = self.stats
        s.calls += 1
        if trace.mode == "observe":
            s.observed += 1
        for q in trace.questions:
            s.questions += 1
            if q.answered_by == "system1":
                s.system1_questions += 1
            else:
                s.system2_questions += 1
                if q.abstain:
                    s.abstain_reasons[q.reason.split(":")[0] or "abstain"] += 1
            if q.system1_answer is not None and q.system2_answer is not None:
                s.shadow_compared += 1
                if q.system1_answer == q.system2_answer:
                    s.shadow_agreed += 1


def uniform_for(question: Question) -> Distribution:
    """The distribution an unfitted or absent System-1 is treated as having."""
    return uniform(question.keys())
