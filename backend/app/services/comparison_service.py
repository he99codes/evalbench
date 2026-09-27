"""Stage 3 (pairwise comparison with position randomization) and stage 4 (improvement)."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.providers.base import LLMProvider, RetryPolicy, StructuredCallResult, call_structured
from app.services.requirement_service import SYSTEM_PROMPT
from app.utils.validation import ImprovementOutput, PairwiseComparisonOutput

CandidateOrder = Literal["AB", "BA"]

PAIRWISE_TEMPLATE = """Compare two candidate responses to the same prompt. Each was already scored independently against the same rubric; use those results and the texts. The candidate numbering is random and carries no meaning.

<prompt>
{prompt}
</prompt>

<candidate id="1">
{candidate_1}
</candidate>

<candidate id="2">
{candidate_2}
</candidate>

<scores candidate="1">
{scores_1}
</scores>

<scores candidate="2">
{scores_2}
</scores>

Return preferred (CANDIDATE_1, CANDIDATE_2 or TIE), reasoning (3-5 sentences that cite the rubric results) and decisive_criteria (names of the criteria that decided the preference)."""

IMPROVEMENT_TEMPLATE = """Suggest ONE concrete improvement for one of the two responses below.

<prompt>
{prompt}
</prompt>

<response label="A">
{response_a}
</response>

<response label="B">
{response_b}
</response>

<results label="A">
{results_a}
</results>

<results label="B">
{results_b}
</results>

<preferred>{preferred}</preferred>

Pick target_response (A or B): the response where a single change would most improve how well it fulfils the prompt. Describe one specific, actionable edit in 1-3 sentences."""


def choose_candidate_order(rng: random.Random | None = None) -> CandidateOrder:
    """Randomly decide whether Response A is shown as Candidate 1 ("AB") or 2 ("BA")."""
    return "AB" if (rng or random.SystemRandom()).random() < 0.5 else "BA"


def map_preference(preferred: str, order: CandidateOrder) -> Literal["A", "B", "TIE"]:
    if preferred == "TIE":
        return "TIE"
    first, second = ("A", "B") if order == "AB" else ("B", "A")
    return first if preferred == "CANDIDATE_1" else second  # type: ignore[return-value]


def anonymize_reasoning(reasoning: str, *, first: Literal["A", "B"], second: Literal["A", "B"]) -> str:
    """Replace every "candidate 1"/"candidate 2" mention with the real response label.

    Real LLM output varies (case, "CANDIDATE_1", non-breaking spaces between the word
    and number, "candidate #1", etc.), so this matches loosely rather than doing exact
    string replacement, which silently misses variants and leaks the anonymized labels
    into what the UI shows the user.
    """
    pattern = re.compile(r"candidate[\s_]*#?\s*([12])", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        label = first if match.group(1) == "1" else second
        return f"Response {label}"

    return pattern.sub(replace, reasoning).strip()


def format_results(results: list[dict[str, Any]]) -> str:
    """One line per criterion result (dicts with name, weight, score, scale, passed, reasoning)."""
    return "\n".join(
        f"- {r['name']} (weight {r['weight']:g}): {r['score']:g} on {r['scale_min']}-{r['scale_max']}, "
        f"{'passed' if r['passed'] else 'failed'}. Reasoning: {r['reasoning']}"
        for r in results
    )


@dataclass
class ComparisonResult:
    preferred_response: Literal["A", "B", "TIE"]
    reasoning: str
    decisive_criteria: list[str]
    candidate_order: CandidateOrder
    call: StructuredCallResult


def compare(
    provider: LLMProvider,
    *,
    prompt: str,
    response_a: str,
    response_b: str,
    results_a: list[dict[str, Any]],
    results_b: list[dict[str, Any]],
    order: CandidateOrder,
    policy: RetryPolicy | None = None,
    sleep=None,
) -> ComparisonResult:
    texts = {"A": response_a, "B": response_b}
    scores = {"A": format_results(results_a), "B": format_results(results_b)}
    first, second = ("A", "B") if order == "AB" else ("B", "A")
    criterion_names = {r["name"] for r in results_a}

    def postprocess(output: PairwiseComparisonOutput) -> PairwiseComparisonOutput:
        if not output.reasoning.strip():
            raise ValueError("empty reasoning")
        return output

    kwargs = {"sleep": sleep} if sleep else {}
    call = call_structured(
        provider,
        PAIRWISE_TEMPLATE.format(
            prompt=prompt,
            candidate_1=texts[first],
            candidate_2=texts[second],
            scores_1=scores[first],
            scores_2=scores[second],
        ),
        PairwiseComparisonOutput,
        system=SYSTEM_PROMPT,
        postprocess=postprocess,
        policy=policy,
        **kwargs,
    )
    output: PairwiseComparisonOutput = call.processed
    reasoning = anonymize_reasoning(output.reasoning, first=first, second=second)
    decisive = [c.strip() for c in output.decisive_criteria if c.strip() in criterion_names]
    return ComparisonResult(map_preference(output.preferred, order), reasoning, decisive, order, call)


def suggest_improvement(
    provider: LLMProvider,
    *,
    prompt: str,
    response_a: str,
    response_b: str,
    results_a: list[dict[str, Any]],
    results_b: list[dict[str, Any]],
    preferred: str,
    policy: RetryPolicy | None = None,
    sleep=None,
) -> StructuredCallResult:
    def postprocess(output: ImprovementOutput) -> ImprovementOutput:
        if not output.improvement.strip():
            raise ValueError("empty improvement")
        return output

    kwargs = {"sleep": sleep} if sleep else {}
    return call_structured(
        provider,
        IMPROVEMENT_TEMPLATE.format(
            prompt=prompt,
            response_a=response_a,
            response_b=response_b,
            results_a=format_results(results_a),
            results_b=format_results(results_b),
            preferred=preferred,
        ),
        ImprovementOutput,
        system=SYSTEM_PROMPT,
        postprocess=postprocess,
        policy=policy,
        **kwargs,
    )
