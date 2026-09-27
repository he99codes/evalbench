"""Stage 1 (requirement extraction) and stage 5 input (per-requirement compliance checks)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import EvaluationStatus, PromptRequirement, RequirementType
from app.providers import get_llm_provider
from app.providers.base import LLMProvider, RetryPolicy, StructuredCallResult, call_structured
from app.schemas.evaluation import AnalyzePromptResponse, PromptRequirementCreate
from app.services import ConflictError
from app.utils.validation import (
    ComplianceCheckOutput,
    ExtractedRequirement,
    RequirementExtractionOutput,
)

SYSTEM_PROMPT = (
    "You are a meticulous evaluator of AI assistant responses. Follow the instructions "
    "exactly and respond only with JSON that matches the provided schema."
)

EXTRACTION_TEMPLATE = """Extract the requirements from the user prompt below.

- requests: tasks the response must perform (type REQUEST).
- constraints: rules the response must respect. Use type CONSTRAINT for forbidden or required content, LENGTH for length limits, AUDIENCE for audience or tone, OTHER otherwise.
- format_requirements: required structure or formatting (type FORMAT).
- ambiguities: parts of the prompt that are unclear or subjective.

For every item give type, a short description, mandatory (true if the prompt requires it, false if it is only a preference) and source_text copied verbatim from the prompt.
Do not invent requirements. Background context, such as a quoted message the reply responds to, is not a requirement.

<prompt>
{prompt}
</prompt>"""

COMPLIANCE_TEMPLATE = """Check whether the response satisfies each requirement. Judge each requirement independently and literally.

<requirements>
{requirements}
</requirements>

<response>
{response}
</response>

Return one check per requirement id ({ids}) with satisfied, a one-sentence explanation, and quote: a verbatim excerpt from the response supporting the judgment, or "" if the requirement concerns something absent."""

_BUCKET_TYPES: dict[str, tuple[RequirementType, set[RequirementType]]] = {
    "requests": (RequirementType.REQUEST, {RequirementType.REQUEST, RequirementType.OTHER}),
    "constraints": (
        RequirementType.CONSTRAINT,
        {
            RequirementType.CONSTRAINT,
            RequirementType.LENGTH,
            RequirementType.AUDIENCE,
            RequirementType.OTHER,
        },
    ),
    "format_requirements": (RequirementType.FORMAT, {RequirementType.FORMAT}),
}


def build_extraction_prompt(prompt: str) -> str:
    return EXTRACTION_TEMPLATE.format(prompt=prompt)


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9$#%]+", " ", text.lower()).strip()


def parse_extraction(
    output: RequirementExtractionOutput,
) -> tuple[list[PromptRequirementCreate], list[str]]:
    """Turn stage-1 output into requirement rows + ambiguities.

    - Each bucket constrains the allowed types; a type that does not fit its bucket is
      coerced to the bucket default (e.g. a FORMAT item inside `requests` -> REQUEST).
    - Blank descriptions are dropped; duplicates (case/punctuation-insensitive) are merged,
      keeping the first occurrence but upgrading it to mandatory if any duplicate is mandatory.
    """
    seen: dict[str, PromptRequirementCreate] = {}
    for bucket, (default_type, allowed) in _BUCKET_TYPES.items():
        items: list[ExtractedRequirement] = getattr(output, bucket)
        for item in items:
            description = item.description.strip()
            key = _normalize_key(description)
            if not key:
                continue
            req_type = RequirementType(item.type)
            if req_type not in allowed:
                req_type = default_type
            if key in seen:
                if item.mandatory and not seen[key].mandatory:
                    seen[key] = seen[key].model_copy(update={"mandatory": True})
                continue
            seen[key] = PromptRequirementCreate(
                type=req_type,
                description=description[:2000],
                mandatory=item.mandatory,
                source_text=item.source_text.strip() or None,
            )
    ambiguities: list[str] = []
    for text in output.ambiguities:
        text = text.strip()
        if text and text not in ambiguities:
            ambiguities.append(text)
    return list(seen.values()), ambiguities


@dataclass
class ExtractedRequirements:
    requirements: list[dict[str, Any]]  # snapshot dicts incl. pre-assigned UUID and short id
    ambiguities: list[str]
    call: StructuredCallResult


def extract_requirements(
    provider: LLMProvider, prompt: str, *, policy: RetryPolicy | None = None, sleep=None
) -> ExtractedRequirements:
    kwargs = {"sleep": sleep} if sleep else {}
    call = call_structured(
        provider,
        build_extraction_prompt(prompt),
        RequirementExtractionOutput,
        system=SYSTEM_PROMPT,
        postprocess=parse_extraction,
        policy=policy,
        **kwargs,
    )
    requirements, ambiguities = call.processed
    snapshot = [
        {
            "id": str(uuid.uuid4()),
            "ref": f"R{index}",
            "type": r.type.value,
            "description": r.description,
            "mandatory": r.mandatory,
            "source_text": r.source_text,
        }
        for index, r in enumerate(requirements, start=1)
    ]
    return ExtractedRequirements(snapshot, ambiguities, call)


def requirement_rows(evaluation_id: uuid.UUID, snapshot: list[dict[str, Any]]) -> list[PromptRequirement]:
    return [
        PromptRequirement(
            id=uuid.UUID(r["id"]),
            evaluation_id=evaluation_id,
            type=RequirementType(r["type"]),
            description=r["description"],
            mandatory=r["mandatory"],
            source_text=r["source_text"],
        )
        for r in snapshot
    ]


def format_requirements(snapshot: list[dict[str, Any]]) -> str:
    if not snapshot:
        return "(no explicit requirements were extracted)"
    return "\n".join(
        f"{r['ref']} [{r['type']}, {'mandatory' if r['mandatory'] else 'optional'}] {r['description']}"
        for r in snapshot
    )


def analyze_prompt(
    db: Session, evaluation_id: uuid.UUID, provider: LLMProvider | None = None
) -> AnalyzePromptResponse:
    """POST /analyze-prompt: run stage 1 and replace the evaluation's requirements."""
    from app.services.evaluation_service import get_evaluation

    evaluation = get_evaluation(db, evaluation_id)
    if evaluation.status == EvaluationStatus.RUNNING:
        raise ConflictError("Evaluation is running; wait for the run to finish")
    extracted = extract_requirements(provider or get_llm_provider(), evaluation.prompt)
    evaluation.requirements.clear()
    db.flush()
    evaluation.requirements.extend(requirement_rows(evaluation.id, extracted.requirements))
    if evaluation.status == EvaluationStatus.DRAFT:
        evaluation.status = EvaluationStatus.READY
    db.commit()
    db.refresh(evaluation)
    return AnalyzePromptResponse(
        evaluation_id=evaluation.id,
        status=evaluation.status,
        requirements=evaluation.requirements,
        ambiguities=extracted.ambiguities,
    )


# ---------------------------------------------------------------------------
# Stage 5 input: per-requirement compliance for one response
# ---------------------------------------------------------------------------


def build_compliance_prompt(snapshot: list[dict[str, Any]], response_text: str) -> str:
    return COMPLIANCE_TEMPLATE.format(
        requirements=format_requirements(snapshot),
        response=response_text,
        ids=", ".join(r["ref"] for r in snapshot) or "none",
    )


def check_compliance(
    provider: LLMProvider,
    snapshot: list[dict[str, Any]],
    response_text: str,
    *,
    policy: RetryPolicy | None = None,
    sleep=None,
) -> StructuredCallResult:
    """Returns a call whose `processed` is a list of checks keyed to requirement UUIDs.

    Every requirement must be judged exactly once; otherwise the output is rejected
    (and retried) rather than silently treating a missing judgment as a pass.
    """
    from app.services.evidence_service import locate_quote

    by_ref = {r["ref"]: r for r in snapshot}

    def postprocess(output: ComplianceCheckOutput) -> list[dict[str, Any]]:
        checks: dict[str, dict[str, Any]] = {}
        for check in output.checks:
            ref = check.requirement_id.strip().upper()
            if ref not in by_ref:
                raise ValueError(f"unknown requirement id {check.requirement_id!r}")
            if ref in checks:
                continue
            quote = check.quote.strip()
            span = locate_quote(response_text, quote) if quote else None
            checks[ref] = {
                "requirement_id": by_ref[ref]["id"],
                "ref": ref,
                "satisfied": check.satisfied,
                "explanation": check.explanation.strip(),
                # Only verbatim quotes are kept; paraphrases are dropped.
                "quote": response_text[span[0] : span[1]] if span else None,
            }
        missing = [ref for ref in by_ref if ref not in checks]
        if missing:
            raise ValueError(f"missing checks for {', '.join(missing)}")
        return [checks[r["ref"]] for r in snapshot]

    kwargs = {"sleep": sleep} if sleep else {}
    return call_structured(
        provider,
        build_compliance_prompt(snapshot, response_text),
        ComplianceCheckOutput,
        system=SYSTEM_PROMPT,
        postprocess=postprocess,
        policy=policy,
        **kwargs,
    )
