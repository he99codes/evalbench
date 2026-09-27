"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from app.models.criterion import Criterion, EvaluationCriterion
from app.models.evaluation import (
    Evaluation,
    EvaluationStatus,
    PreferredResponse,
    PromptRequirement,
    RequirementType,
)
from app.models.evidence import EvidenceItem
from app.models.project import Project
from app.models.result import EvaluationResult, ResponseLabel
from app.models.run import EvaluationRun, RunStatus

__all__ = [
    "Criterion",
    "Evaluation",
    "EvaluationCriterion",
    "EvaluationResult",
    "EvaluationRun",
    "EvaluationStatus",
    "EvidenceItem",
    "PreferredResponse",
    "Project",
    "PromptRequirement",
    "RequirementType",
    "ResponseLabel",
    "RunStatus",
]
