"""Shared fixtures. The only example capability in this repository is ``support.triage``."""
from __future__ import annotations

from praxis.core.contracts import Answer, Capability, Question, State

DEPARTMENTS = {"billing": "Invoices, charges, refunds and payment methods.",
               "technical": "Errors, outages, crashes, logins and integrations.",
               "account": "Profile, email, password and access changes.",
               "sales": "Pricing, plans, upgrades and quotes."}
URGENCY = ("low: no deadline, can wait a week", "medium: wants an answer within a few days",
           "high: blocked, needs help today", "critical: service down or money at risk, act now")


def triage_capability() -> Capability:
    return Capability(
        name="support.triage",
        description="Route an inbound support ticket.",
        questions={
            "department": Question.choice("Which team should handle this ticket?", DEPARTMENTS),
            "urgency": Question.score("How urgent is this ticket?", URGENCY),
            "churn_risk": Question.boolean("The customer is at risk of cancelling."),
        })


def oracle(state: State, name: str, question: Question) -> Answer:
    """A keyword teacher, so tests have a System-2 that reads the state."""
    text = (state if isinstance(state, str) else " ".join(str(v) for v in state.values())).lower()
    if name == "department":
        for key, words in (("billing", ("invoice", "charge", "refund", "payment")),
                           ("technical", ("error", "crash", "outage", "login", "api")),
                           ("account", ("password", "email", "profile", "access")),
                           ("sales", ("pricing", "upgrade", "quote", "plan"))):
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
