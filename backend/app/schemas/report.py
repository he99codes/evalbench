"""Report payload: everything the UI renders is computed server-side and returned here."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import EvaluationStatus, PreferredResponse, RequirementType, ResponseLabel
from app.schemas.evaluation import EvaluationRunRead, EvidenceItemRead


class RequirementCheckRead(BaseModel):
    satisfied: bool
    explanation: str
    quote: str | None


class ReportRequirement(BaseModel):
    id: uuid.UUID
    ref: str
    type: RequirementType
    description: str
    mandatory: bool
    source_text: str | None
    compliance_a: RequirementCheckRead | None
    compliance_b: RequirementCheckRead | None


class CriterionSide(BaseModel):
    result_id: uuid.UUID
    score: float
    normalized_score: float  # 0-1
    passed: bool
    reasoning: str
    evidence: list[EvidenceItemRead]


class ReportCriterionRow(BaseModel):
    criterion_id: uuid.UUID
    name: str
    description: str
    weight: float
    weight_share: float  # weight / total weight, 0-1
    scale_min: int
    scale_max: int
    a: CriterionSide
    b: CriterionSide
    leader: PreferredResponse  # which response scored higher on this criterion
    decisive: bool


class ResponseSummary(BaseModel):
    label: ResponseLabel
    overall_score: float  # 0-100, deterministic weighted aggregate
    criteria_passed: int
    criteria_total: int
    mandatory_satisfied: int
    mandatory_total: int
    compliance_rate: float | None  # 0-100


class PreferenceRead(BaseModel):
    preferred_response: PreferredResponse
    reasoning: str
    decisive_criteria: list[str]
    candidate_order: str | None
    score_leader: PreferredResponse
    agrees_with_scores: bool


class ImprovementRead(BaseModel):
    target_response: ResponseLabel
    improvement: str


class ResponseMismatchRead(BaseModel):
    overall_score: float
    compliance_rate: float | None
    gap: float | None
    flagged: bool


class RewardMismatchRead(BaseModel):
    flagged: bool
    threshold: float
    a: ResponseMismatchRead
    b: ResponseMismatchRead
    preferred_less_compliant: bool
    score_leader_less_compliant: bool
    reasons: list[str]


class EvidenceEntry(BaseModel):
    criterion_id: uuid.UUID
    criterion_name: str
    score: float
    scale_max: int
    passed: bool
    quote: str
    supports: str
    location: str | None


class ReportEvaluation(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: EvaluationStatus
    prompt: str
    response_a: str
    response_b: str
    created_at: datetime


class ReportRead(BaseModel):
    evaluation: ReportEvaluation
    run: EvaluationRunRead
    requirements: list[ReportRequirement]
    ambiguities: list[str]
    criteria: list[ReportCriterionRow]
    summary_a: ResponseSummary
    summary_b: ResponseSummary
    preference: PreferenceRead
    improvement: ImprovementRead
    reward_mismatch: RewardMismatchRead
    evidence_a: list[EvidenceEntry]
    evidence_b: list[EvidenceEntry]


# ---------------------------------------------------------------------------
# Project analytics (Phase 8)
# ---------------------------------------------------------------------------


class PreferenceCounts(BaseModel):
    A: int = 0
    B: int = 0
    TIE: int = 0


class CriterionFailureStat(BaseModel):
    criterion_id: uuid.UUID
    name: str
    evaluated: int  # response-level results (2 per completed evaluation)
    failed: int
    pass_rate: float  # 0-100


class PreferencePoint(BaseModel):
    date: str  # YYYY-MM-DD (completion date of the evaluation's latest run)
    A: int
    B: int
    TIE: int


class ProjectAnalytics(BaseModel):
    project_id: uuid.UUID
    total_evaluations: int
    completed_evaluations: int
    preference: PreferenceCounts
    average_score_a: float | None
    average_score_b: float | None
    average_quality: float | None  # mean of all response overall scores (0-100)
    constraint_compliance_rate: float | None  # mandatory checks satisfied / total (0-100)
    mandatory_checks_total: int
    mandatory_checks_satisfied: int
    reward_mismatch_count: int
    most_common_failing_criterion: CriterionFailureStat | None
    criteria: list[CriterionFailureStat]
    preference_over_time: list[PreferencePoint]


# ---------------------------------------------------------------------------
# Evaluator agreement between two runs (Phase 9)
# ---------------------------------------------------------------------------


class AgreementRunInfo(BaseModel):
    run_id: uuid.UUID
    run_number: int  # 1-based position in the evaluation's run history
    provider: str
    evaluator_model: str
    rubric_version: str
    prompt_version: str
    candidate_order: str | None
    preferred_response: PreferredResponse
    overall_score_a: float
    overall_score_b: float


class CriterionAgreement(BaseModel):
    criterion_id: uuid.UUID
    name: str
    response: ResponseLabel
    score_1: float
    score_2: float
    scale_min: int
    scale_max: int
    normalized_difference: float  # |norm1 - norm2|, 0-1
    passed_1: bool
    passed_2: bool
    pass_agrees: bool


class AgreementRead(BaseModel):
    evaluation_id: uuid.UUID
    run_1: AgreementRunInfo
    run_2: AgreementRunInfo
    same_rubric: bool
    same_prompt_version: bool
    same_evaluator: bool
    preference_agrees: bool
    criteria: list[CriterionAgreement]  # criteria scored in both runs, for A and B
    criteria_only_in_one_run: list[str]
    pass_fail_agreement: float | None  # % of (criterion, response) pass/fail judgments that match
    mean_abs_score_difference: float | None  # mean normalized difference, 0-1
    overall_score_difference_a: float  # run_2 - run_1, percentage points
    overall_score_difference_b: float
    # % of all categorical judgments that match: the preference + every pass/fail judgment.
    overall_agreement: float
