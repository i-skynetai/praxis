"""praxis.core — the contract, the ports, and the stdlib-only machinery behind them.

Nothing in this package imports anything outside the Python standard library, and no
provider or product name appears here. Providers live in `praxis.providers`.
"""
from .contracts import (
    ENVELOPE_VERSION,
    Answer,
    Budget,
    Capability,
    DecisionExample,
    DecisionRequest,
    DecisionResult,
    Distribution,
    GenerativeAnswer,
    ModelArtifact,
    ModelInfo,
    Question,
    QuestionTrace,
    RawAnswer,
    RequestContext,
    State,
    TeacherAnswer,
    TraceEvent,
    normalise_question_type,
)
from .ports import (
    Calibrator,
    DecisionModel,
    GenerativeModel,
    Registry,
    SchemaValidator,
    Teacher,
    Trainer,
    TraceSink,
)

__all__ = [
    "ENVELOPE_VERSION", "Answer", "Budget", "Capability", "DecisionExample",
    "DecisionRequest", "DecisionResult", "Distribution", "GenerativeAnswer",
    "ModelArtifact", "ModelInfo", "Question", "QuestionTrace", "RawAnswer",
    "RequestContext", "State", "TeacherAnswer", "TraceEvent", "normalise_question_type",
    "Calibrator", "DecisionModel", "GenerativeModel", "Registry", "SchemaValidator",
    "Teacher", "Trainer", "TraceSink",
]
