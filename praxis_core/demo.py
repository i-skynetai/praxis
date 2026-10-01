"""``python -m praxis demo``: the whole loop on one capability, with nothing installed.

``support.triage`` asks three questions of a support ticket: ``department`` (a choice of
four), ``urgency`` (a score on four levels) and ``churn_risk`` (a boolean). A synthetic
ticket generator produces the traffic, a keyword rule stands in for the System-2
teacher, and the nearest-neighbour baseline is the System-1 student.

Four stages, in the order the plan says to trust the loop before the model:

1. ``shadow`` with an unfitted student: every answer comes from the teacher; the trace
   records that System-1 had nothing to say.
2. The teacher's answers become labels, the student is fitted, and a second ``shadow``
   pass records both answers side by side. Those traces fit the calibrator.
3. ``canary``: half the calls may be served by System-1 when it is confident.
4. ``serve``: every confident, valid answer is System-1's; the rest abstain to the teacher.

The last line reports how many System-1 answers the teacher would have disagreed with,
because that is the number this project exists to keep small.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from praxis_core.baseline import NearestNeighbourDecisionModel
from praxis_core.calibrate import TemperatureCalibrator
from praxis_core.contracts import Answer, Capability, Question, State
from praxis_core.dataset import examples_from_traces
from praxis_core.ports import TraceSink
from praxis_core.router import DecisionRouter, RoutingPolicy
from praxis_core.providers.fake import FakeTeacher, FakeTraceSink

DEPARTMENTS = {
    "billing": "Invoices, charges, refunds and payment methods.",
    "technical": "Errors, outages, crashes, logins and integrations.",
    "account": "Profile, email, password and access changes.",
    "sales": "Pricing, plans, upgrades and quotes.",
}
URGENCY = (
    "low: no deadline, can wait a week",
    "medium: wants an answer within a few days",
    "high: blocked, needs help today",
    "critical: service down or money at risk, act now",
)


def support_triage() -> Capability:
    """The only example capability in this repository."""
    return Capability(
        name="support.triage",
        description="Route an inbound support ticket: which team, how urgent, is the customer at risk.",
        questions={
            "department": Question.choice("Which team should handle this ticket?", DEPARTMENTS),
            "urgency": Question.score("How urgent is this ticket?", URGENCY),
            "churn_risk": Question.boolean("The customer is at risk of cancelling."),
        })


# ------------------------------------------------------------------ the teacher

_DEPARTMENT_WORDS = (
    ("billing", ("invoice", "charge", "charged", "refund", "payment")),
    ("technical", ("error", "crash", "crashes", "outage", "login", "api")),
    ("account", ("password", "email", "profile", "access")),
    ("sales", ("pricing", "upgrade", "quote", "plan")),
)


def _text(state: State) -> str:
    return (state if isinstance(state, str) else " ".join(str(v) for v in state.values())).lower()


def rule_teacher(state: State, name: str, question: Question) -> Answer:
    """A keyword System-2. It reads the ticket; it never sees the generator's choices."""
    text = _text(state)
    if name == "department":
        for key, words in _DEPARTMENT_WORDS:
            if any(w in text for w in words):
                return key
        return "technical"
    if name == "urgency":
        if "down" in text or "act now" in text:
            return 3
        if "today" in text:
            return 2
        if "this week" in text or "few days" in text:
            return 1
        return 0
    if name == "churn_risk":
        return any(w in text for w in ("cancel", "competitor", "switch"))
    raise KeyError(name)


# ---------------------------------------------------------------- the traffic

_DEPARTMENT_PHRASES = {
    "billing": ("my invoice shows a charge I do not recognise", "the payment failed but my card was charged",
                "I need a refund for last month", "why was I charged twice on the invoice",
                "the payment page keeps rejecting my card", "please resend the invoice for March"),
    "technical": ("the login page throws an error", "the app crashes when I export",
                  "your api returns a 500 error", "we have an outage on the dashboard",
                  "the integration fails with a timeout error", "login keeps failing with an unknown error"),
    "account": ("I cannot reset my password", "please change the email on my profile",
                "I need access for a new team member", "my profile shows the wrong name",
                "the password reset email never arrives", "remove access for a former employee"),
    "sales": ("what is the pricing for 50 seats", "we want to upgrade to the enterprise plan",
              "can you send a quote for annual billing", "which plan includes audit logs",
              "we are comparing plans before we upgrade", "I need a quote for the team plan"),
}
_URGENCY_PHRASES = (
    ("no rush at all, whenever you get to it", "low priority, just letting you know"),
    ("it would be good to have this sorted this week", "could you look at this in the next few days"),
    ("we need this today, our team is blocked", "this has to be fixed today"),
    ("our service is down for all customers, act now", "everything is down, please act now"),
)
_CHURN_PHRASES = (
    ("if this is not fixed we will cancel", "we are evaluating a competitor", "we might switch providers"),
    ("thanks for the help so far", "we are otherwise happy with the product", "appreciate a quick reply"),
)
_GREETINGS = ("hi", "hello", "hi team", "quick one", "good morning", "hey there")


class TicketGenerator:
    """Deterministic for a seed. Produces ``{"subject", "body"}`` states."""

    def __init__(self, seed: int = 7) -> None:
        self._rng = random.Random(seed)

    def ticket(self) -> dict[str, str]:
        rng = self._rng
        department = rng.choice(list(_DEPARTMENT_PHRASES))
        problem = rng.choice(_DEPARTMENT_PHRASES[department])
        urgency = rng.choice(_URGENCY_PHRASES[rng.randrange(4)])
        churn = rng.choice(_CHURN_PHRASES[0] if rng.random() < 0.3 else _CHURN_PHRASES[1])
        subject = " ".join(problem.split()[:4])
        body = f"{rng.choice(_GREETINGS)}, {problem}. {urgency}. {churn}."
        return {"subject": subject, "body": body}

    def tickets(self, n: int) -> list[dict[str, str]]:
        return [self.ticket() for _ in range(n)]


# ------------------------------------------------------------------- the loop

@dataclass
class StageReport:
    stage: str
    calls: int
    questions: int
    system1_share: float
    abstain_share: float
    agreement: float | None
    elapsed_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "calls": self.calls, "questions": self.questions,
                "system1_share": round(self.system1_share, 4), "abstain_share": round(self.abstain_share, 4),
                "agreement": None if self.agreement is None else round(self.agreement, 4),
                "elapsed_ms": round(self.elapsed_ms, 1)}


@dataclass
class DemoSummary:
    stages: list[StageReport] = field(default_factory=list)
    temperatures: dict[str, float] = field(default_factory=dict)
    examples: int = 0
    served_by_system1: int = 0
    confident_wrong: int = 0
    trace_count: int = 0
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"stages": [s.as_dict() for s in self.stages], "temperatures": self.temperatures,
                "examples": self.examples, "served_by_system1": self.served_by_system1,
                "confident_wrong": self.confident_wrong, "trace_count": self.trace_count,
                "elapsed_ms": round(self.elapsed_ms, 1)}


def _run_stage(router: DecisionRouter, generator: TicketGenerator, n: int, label: str) -> StageReport:
    before = router.stats.as_dict()
    started = time.perf_counter()
    for ticket in generator.tickets(n):
        router.decide_state(ticket)
    elapsed = (time.perf_counter() - started) * 1000.0
    after = router.stats.as_dict()
    questions = after["questions"] - before["questions"]
    system1 = after["system1_questions"] - before["system1_questions"]
    abstained = sum(after["abstain_reasons"].values()) - sum(before["abstain_reasons"].values())
    compared = after["shadow_compared"] - before["shadow_compared"]
    agreed = after["shadow_agreed"] - before["shadow_agreed"]
    return StageReport(label, n, questions, system1 / questions if questions else 0.0,
                       abstained / questions if questions else 0.0,
                       agreed / compared if compared else None, elapsed)


def run_demo(tickets: int = 60, threshold: float = 0.5, seed: int = 7, sink: TraceSink | None = None,
             out: Callable[[str], None] | None = print) -> DemoSummary:
    say = out or (lambda _line: None)
    started = time.perf_counter()
    capability = support_triage()
    generator = TicketGenerator(seed)
    teacher = FakeTeacher(rule_teacher)
    student = NearestNeighbourDecisionModel()
    calibrator = TemperatureCalibrator(min_examples=10)
    sink = sink if sink is not None else FakeTraceSink()
    router = DecisionRouter(capability, teacher, student, calibrator, sink,
                            RoutingPolicy(threshold=threshold, stage="shadow", canary_share=0.5),
                            rng=random.Random(seed), source="synthetic")
    summary = DemoSummary()

    say(f"praxis demo: {capability.name}, {len(capability.questions)} questions, fake teacher, "
        f"{student.name} student, threshold {threshold}")
    say("")
    say(f"{'stage':<14}{'calls':>6}{'questions':>11}{'system1':>9}{'abstain':>9}{'agree':>8}{'ms':>7}")

    def show(report: StageReport) -> None:
        summary.stages.append(report)
        agree = "-" if report.agreement is None else f"{report.agreement:.2f}"
        say(f"{report.stage:<14}{report.calls:>6}{report.questions:>11}{report.system1_share:>8.0%} "
            f"{report.abstain_share:>8.0%}{agree:>8}{report.elapsed_ms:>7.1f}")

    show(_run_stage(router, generator, tickets, "shadow-cold"))          # 1. capture with nothing to say

    examples, report = examples_from_traces(sink.read(capability.name), capability)
    summary.examples = student.fit(examples)                              # 2. labels → student
    show(_run_stage(router, generator, tickets, "shadow-warm"))           #    both answers side by side
    summary.temperatures = dict(calibrator.fit(list(sink.read(capability.name))))  # → calibrator

    router.set_stage("canary")                                            # 3. half the calls may be served
    show(_run_stage(router, generator, tickets, "canary-50%"))

    router.set_stage("serve")                                             # 4. serve when confident
    served_states: list[tuple[dict[str, str], str, Answer]] = []
    serve_started = time.perf_counter()
    before = router.stats.as_dict()
    for ticket in generator.tickets(tickets):
        for name, result in router.decide_state(ticket).items():
            if result.answered_by == "system1":
                served_states.append((ticket, name, result.answer))
    after = router.stats.as_dict()
    questions = after["questions"] - before["questions"]
    show(StageReport("serve", tickets, questions,
                     (after["system1_questions"] - before["system1_questions"]) / questions if questions else 0.0,
                     (sum(after["abstain_reasons"].values()) - sum(before["abstain_reasons"].values())) / questions
                     if questions else 0.0, None, (time.perf_counter() - serve_started) * 1000.0))

    # The number to watch: served by System-1, and the teacher would have said otherwise.
    for ticket, name, answer in served_states:
        if teacher.answer(ticket, {name: capability.questions[name]})[name].answer != answer:
            summary.confident_wrong += 1
    summary.served_by_system1 = len(served_states)
    summary.trace_count = sum(1 for _ in sink.read(capability.name))
    summary.elapsed_ms = (time.perf_counter() - started) * 1000.0

    say("")
    temps = "  ".join(f"{k} T={v:.2f}" for k, v in summary.temperatures.items()) or "none fitted"
    say(f"calibrator: {temps}")
    say(f"labels: {report['examples']} System-2 answers from {report['traces']} traces -> "
        f"{summary.examples} examples -> student fitted")
    say(f"served by System-1 in the serve stage: {summary.served_by_system1}; the teacher would have "
        f"disagreed on {summary.confident_wrong} (confident-wrong)")
    say(f"{summary.trace_count} traces recorded; the trace path raised into the caller "
        f"{router.stats.trace_failures} times")
    say(f"loop closed in {summary.elapsed_ms:.0f} ms: capture -> label -> fit -> calibrate -> canary -> serve. "
        f"The teacher stays.")
    return summary
