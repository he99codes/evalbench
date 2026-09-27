import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.models import (
    EvaluationStatus,
    PreferredResponse,
    RequirementType,
    ResponseLabel,
    RunStatus,
)
from app.schemas.criterion import CriterionRead
from app.utils.validation import NonBlankName, NonBlankText, Weight, reject_explicit_nulls

# ---------------------------------------------------------------------------
# Criteria selection (evaluation_criteria)
# ---------------------------------------------------------------------------


class EvaluationCriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: uuid.UUID
    # Omitted -> the criterion's project default weight is snapshotted.
    weight: Weight | None = None


def _validate_selection(criteria: list[EvaluationCriterionInput]) -> None:
    ids = [c.criterion_id for c in criteria]
    if len(ids) != len(set(ids)):
        raise ValueError("criteria must not contain duplicate criterion_id values")
    explicit = [c.weight for c in criteria if c.weight is not None]
    if len(explicit) == len(criteria) and sum(explicit) <= 0:
        raise ValueError("at least one selected criterion must have a weight greater than 0")


class EvaluationCriterionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    criterion_id: uuid.UUID
    weight: float
    criterion: CriterionRead


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


class EvaluationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    title: NonBlankName
    prompt: NonBlankText
    response_a: NonBlankText
    response_b: NonBlankText
    criteria: list[EvaluationCriterionInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _criteria(self) -> "EvaluationCreate":
        _validate_selection(self.criteria)
        return self


class EvaluationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankName | None = None
    prompt: NonBlankText | None = None
    response_a: NonBlankText | None = None
    response_b: NonBlankText | None = None
    criteria: list[EvaluationCriterionInput] | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def _checks(self) -> "EvaluationUpdate":
        reject_explicit_nulls(self, "title", "prompt", "response_a", "response_b", "criteria")
        if self.criteria is not None:
            _validate_selection(self.criteria)
        return self


class EvaluationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: EvaluationStatus
    preferred_response: PreferredResponse | None
    overall_score_a: float | None
    overall_score_b: float | None
    created_at: datetime
    updated_at: datetime


class PromptRequirementCreate(BaseModel):
    """Internal contract used by requirement_service when persisting stage 1 output."""

    type: RequirementType
    description: NonBlankName = Field(max_length=2_000)
    mandatory: bool = True
    source_text: str | None = Field(default=None, max_length=5_000)


class PromptRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evaluation_id: uuid.UUID
    type: RequirementType
    description: str
    mandatory: bool
    source_text: str | None
    created_at: datetime


class EvaluationRead(EvaluationSummary):
    prompt: str
    response_a: str
    response_b: str
    final_reasoning: str | None
    improvement: str | None
    criteria: list[EvaluationCriterionRead] = Field(validation_alias="criteria_links")
    requirements: list[PromptRequirementRead]


class AnalyzePromptResponse(BaseModel):
    evaluation_id: uuid.UUID
    status: EvaluationStatus
    requirements: list[PromptRequirementRead]
    ambiguities: list[str]


# ---------------------------------------------------------------------------
# Results, evidence and runs (created only by the pipeline)
# ---------------------------------------------------------------------------


class EvidenceItemCreate(BaseModel):
    response: ResponseLabel
    quote: NonBlankText
    supports: NonBlankName = Field(max_length=2_000)
    location: str | None = None


class EvidenceItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evaluation_result_id: uuid.UUID
    response: ResponseLabel
    quote: str
    location: str | None
    supports: str
    created_at: datetime


class EvaluationResultCreate(BaseModel):
    criterion_id: uuid.UUID
    response: ResponseLabel
    score: float
    passed: bool
    reasoning: NonBlankText
    # Never store a criterion score without evidence.
    evidence: list[EvidenceItemCreate] = Field(min_length=1)


class EvaluationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evaluation_id: uuid.UUID
    run_id: uuid.UUID
    criterion_id: uuid.UUID
    response: ResponseLabel
    score: float
    passed: bool
    reasoning: str
    created_at: datetime
    evidence: list[EvidenceItemRead]


class EvaluationRunCreate(BaseModel):
    """Metadata required before any run starts (reproducibility)."""

    evaluator_model: NonBlankName
    provider: NonBlankName
    rubric_version: NonBlankName
    prompt_version: NonBlankName


class RunProgress(BaseModel):
    stage: str | None = None
    completed_steps: int = 0
    total_steps: int = 0


class RunError(BaseModel):
    stage: str | None = None
    type: str
    message: str


class RunOutcome(BaseModel):
    overall_score_a: float
    overall_score_b: float
    preferred_response: PreferredResponse


class EvaluationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evaluation_id: uuid.UUID
    evaluator_model: str
    provider: str
    rubric_version: str
    prompt_version: str
    status: RunStatus
    candidate_order: str | None
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    completed_at: datetime | None
    raw_output: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def progress(self) -> RunProgress:
        return RunProgress.model_validate(self.raw_output.get("progress") or {})

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error(self) -> RunError | None:
        error = self.raw_output.get("error")
        return RunError.model_validate(error) if error else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def outcome(self) -> RunOutcome | None:
        """Per-run verdict, so runs can be compared without loading full reports."""
        scores = self.raw_output.get("scores")
        comparison = (self.raw_output.get("stages") or {}).get("pairwise_comparison")
        if self.status != RunStatus.COMPLETED or not scores or not comparison:
            return None
        return RunOutcome(
            overall_score_a=scores["overall_score_a"],
            overall_score_b=scores["overall_score_b"],
            preferred_response=comparison["preferred_response"],
        )


class EvaluationRunDetail(EvaluationRunRead):
    """Run including the full raw_output JSONB (per-stage LLM outputs)."""

    raw_output: dict[str, Any] = Field(default_factory=dict)
