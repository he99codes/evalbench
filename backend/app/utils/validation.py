"""Reusable validation primitives shared by API schemas and pipeline contracts."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_TEXT_LENGTH = 50_000


def _non_blank_stripped(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be empty or whitespace")
    return stripped


def _non_blank_preserved(value: str) -> str:
    # Long-form text is stored verbatim (evidence offsets depend on it),
    # but whitespace-only content is rejected.
    if not value.strip():
        raise ValueError("must not be empty or whitespace")
    return value


# Short labels (names, titles): trimmed.
NonBlankName = Annotated[str, Field(max_length=300), AfterValidator(_non_blank_stripped)]
# Prompts and responses: stored as given, must contain non-whitespace text.
NonBlankText = Annotated[str, Field(max_length=MAX_TEXT_LENGTH), AfterValidator(_non_blank_preserved)]

# Weights must be finite and non-negative; the cap keeps weight sets sane.
Weight = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


def reject_explicit_nulls(model: BaseModel, *fields: str) -> None:
    """For PATCH schemas: a non-nullable column may be omitted but not set to null."""
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} cannot be null")


# ---------------------------------------------------------------------------
# Pipeline stage output contracts. Every LLM output is validated against one of
# these before it is used. They double as the JSON schemas sent to the provider,
# so every field is required (strict structured-output mode).
# ---------------------------------------------------------------------------

RequirementTypeLiteral = Literal["REQUEST", "CONSTRAINT", "FORMAT", "AUDIENCE", "LENGTH", "OTHER"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ExtractedRequirement(_Contract):
    type: RequirementTypeLiteral
    description: str = Field(description="Short statement of the requirement")
    mandatory: bool = Field(description="True if required, false if only a preference")
    source_text: str = Field(description="Verbatim excerpt of the prompt this comes from")


class RequirementExtractionOutput(_Contract):
    """Stage 1."""

    requests: list[ExtractedRequirement]
    constraints: list[ExtractedRequirement]
    format_requirements: list[ExtractedRequirement]
    ambiguities: list[str]


class EvidenceQuote(_Contract):
    quote: str = Field(description="Exact, verbatim excerpt copied from the response")
    supports: str = Field(description="What this quote demonstrates for the criterion")


class CriterionEvaluationOutput(_Contract):
    """Stage 2 (one criterion, one response)."""

    criterion: str
    score: float
    passed: bool
    reasoning: str
    evidence: list[EvidenceQuote]


class PairwiseComparisonOutput(_Contract):
    """Stage 3. Candidates are anonymised; mapping back to A/B happens in comparison_service."""

    preferred: Literal["CANDIDATE_1", "CANDIDATE_2", "TIE"]
    reasoning: str
    decisive_criteria: list[str]


class ImprovementOutput(_Contract):
    """Stage 4."""

    target_response: Literal["A", "B"]
    improvement: str


class RequirementCheck(_Contract):
    requirement_id: str = Field(description="Requirement id such as R1")
    satisfied: bool
    explanation: str
    quote: str = Field(description='Verbatim excerpt from the response, or "" if none applies')


class ComplianceCheckOutput(_Contract):
    """Stage 5 (one response): per-requirement compliance used for the reward-mismatch check."""

    checks: list[RequirementCheck]
