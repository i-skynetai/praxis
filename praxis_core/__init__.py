"""Praxis: a provider-neutral System-1 / System-2 decision and training framework.

    capture  ->  gate  ->  train  ->  evaluate  ->  route (with a permanent fallback)

A capability declares what it asks of a state: typed questions, or an output schema.
The app's own main model answers today; Praxis captures those answers, turns them into
a dataset, fits a small student of any kind, measures it against the main model on
identical inputs, and serves it by confidence with the main model as the permanent
fallback. Every call leaves a trace.

Distribution ``praxis-core``, import ``praxis_core``, command ``praxis``. The contracts
and the ports live at the top of this package; adapters in ``praxis_core.providers``;
the original v0.1 modules in ``praxis_core.legacy`` until their replacements land.
``python -m praxis_core demo`` runs the whole loop with nothing installed.
"""

from praxis_core.contracts import (
    Capability,
    DecisionExample,
    DecisionRequest,
    DecisionResult,
    ModelInfo,
    Question,
    RequestContext,
    TraceEvent,
)
from praxis_core.ports import (
    Calibrator,
    DecisionModel,
    GenerativeModel,
    Registry,
    SchemaValidator,
    Teacher,
    TraceSink,
    Trainer,
)
from praxis_core.router import DecisionRouter, RoutingPolicy, TeacherError

__version__ = "0.3.1"

__all__ = [
    "Calibrator",
    "Capability",
    "DecisionExample",
    "DecisionModel",
    "DecisionRequest",
    "DecisionResult",
    "DecisionRouter",
    "GenerativeModel",
    "ModelInfo",
    "Question",
    "Registry",
    "RequestContext",
    "RoutingPolicy",
    "SchemaValidator",
    "Teacher",
    "TeacherError",
    "TraceEvent",
    "TraceSink",
    "Trainer",
    "__version__",
]
