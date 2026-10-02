"""Shared fixtures. The example capabilities are ``support.triage`` (decision) and
``support.extract`` (generative), defined once in ``praxis_core.demo`` and used from there."""

from __future__ import annotations

from typing import Any

from praxis_core.demo import DEPARTMENTS, URGENCY, TicketGenerator, rule_teacher, support_triage
from praxis_core.router import RoutingPolicy

oracle = rule_teacher
triage_capability = support_triage


def serving(threshold: float = 0.5, **changes: Any) -> RoutingPolicy:
    """The explicit opt-out of the safe defaults (PX-900): serve System-1 without a fitted
    calibrator. The fault-injection and serve/abstain tests exercise the serving path with
    fakes and no calibrator, and say so here; a production policy says it on purpose or
    not at all."""
    settings: dict[str, Any] = {"stage": "serve", "require_calibrated": False}
    settings.update(changes)
    return RoutingPolicy(threshold, **settings)


__all__ = ["DEPARTMENTS", "URGENCY", "TicketGenerator", "oracle", "serving", "triage_capability"]
