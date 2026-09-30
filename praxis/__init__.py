"""Praxis: a provider-neutral System-1 / System-2 decision and training framework.

    capture  ->  gate  ->  train  ->  evaluate  ->  route (with a permanent fallback)

A capability declares typed questions. A System-1 decision model answers them in
milliseconds with a distribution; Praxis calibrates it, computes one confidence, and
serves the answer or abstains to the System-2 teacher. Every call leaves a trace, and
the teacher's answers become the labels that train the next System-1.

The decision contract and the ports live in ``praxis.core``; adapters in
``praxis.providers``. The original seam/gate/student modules remain for the generative
path. ``python -m praxis demo`` runs the whole loop with nothing installed.
"""
from praxis.core.contracts import (
    Capability,
    DecisionExample,
    DecisionRequest,
    DecisionResult,
    Question,
    RequestContext,
    TraceEvent,
)
from praxis.core.router import DecisionRouter, RoutingPolicy, TeacherError

__version__ = "0.2.0.dev0"

__all__ = ["Capability", "DecisionExample", "DecisionRequest", "DecisionResult", "DecisionRouter",
           "Question", "RequestContext", "RoutingPolicy", "TeacherError", "TraceEvent", "__version__"]
