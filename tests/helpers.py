"""Shared fixtures. The only example capability in this repository is ``support.triage``,
defined once in ``praxis.demo`` and re-exported here for the tests."""
from __future__ import annotations

from praxis_core.demo import DEPARTMENTS, URGENCY, TicketGenerator, rule_teacher, support_triage

oracle = rule_teacher
triage_capability = support_triage

__all__ = ["DEPARTMENTS", "URGENCY", "TicketGenerator", "oracle", "triage_capability"]
