"""Deterministic scoring. Aggregates are computed here from stored per-criterion
scores and weights; an LLM-reported aggregate or winner is never trusted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

# A preference/leader difference smaller than this (in percentage points) is a tie.
TIE_MARGIN = 0.5
# Reward mismatch: aggregate score exceeds mandatory-requirement compliance by this many points.
MISMATCH_GAP_THRESHOLD = 20.0


class ScoringError(ValueError):
    """Invalid scoring input (missing criterion, bad weight, score outside scale)."""


@dataclass(frozen=True)
class CriterionWeight:
    criterion_id: str
    weight: float
    scale_min: float
    scale_max: float


def normalize(score: float, scale_min: float, scale_max: float) -> float:
    """Map a score on [scale_min, scale_max] to [0, 1]."""
    if not scale_min < scale_max:
        raise ScoringError(f"invalid scale {scale_min}-{scale_max}")
    if not math.isfinite(score) or not scale_min <= score <= scale_max:
        raise ScoringError(f"score {score} outside scale {scale_min}-{scale_max}")
    return (score - scale_min) / (scale_max - scale_min)


def normalized_weights(weights: Sequence[CriterionWeight]) -> dict[str, float]:
    if not weights:
        raise ScoringError("no criteria to score")
    for w in weights:
        if not math.isfinite(w.weight) or w.weight < 0:
            raise ScoringError(f"invalid weight {w.weight} for criterion {w.criterion_id}")
    total = sum(w.weight for w in weights)
    if total <= 0:
        raise ScoringError("total weight must be greater than 0")
    return {w.criterion_id: w.weight / total for w in weights}


def aggregate_score(weights: Sequence[CriterionWeight], scores: Mapping[str, float]) -> float:
    """overall = sum(normalized_score * weight) / sum(weight), as 0-100 rounded to 2 dp.

    A criterion with weight > 0 but no score raises (never silently skipped).
    Zero-weight criteria may be missing. Extra scores for unknown criteria raise.
    """
    shares = normalized_weights(weights)
    unknown = set(scores) - set(shares)
    if unknown:
        raise ScoringError(f"scores for unknown criteria: {sorted(unknown)}")
    total = 0.0
    for w in weights:
        if w.weight == 0:
            continue
        if w.criterion_id not in scores:
            raise ScoringError(f"missing score for criterion {w.criterion_id}")
        total += normalize(scores[w.criterion_id], w.scale_min, w.scale_max) * shares[w.criterion_id]
    return round(total * 100, 2)


Leader = Literal["A", "B", "TIE"]


def score_leader(score_a: float, score_b: float, margin: float = TIE_MARGIN) -> Leader:
    if abs(score_a - score_b) < margin:
        return "TIE"
    return "A" if score_a > score_b else "B"


def compliance_rate(satisfied: Sequence[bool]) -> float | None:
    """Share (0-100) of mandatory requirements satisfied; None when there are none."""
    if not satisfied:
        return None
    return round(100 * sum(1 for s in satisfied if s) / len(satisfied), 2)


@dataclass
class ResponseMismatch:
    overall_score: float
    compliance_rate: float | None
    gap: float | None
    flagged: bool


@dataclass
class RewardMismatch:
    flagged: bool
    threshold: float
    responses: dict[str, ResponseMismatch]
    preferred_less_compliant: bool
    score_leader_less_compliant: bool
    reasons: list[str] = field(default_factory=list)


def detect_reward_mismatch(
    *,
    overall_a: float,
    overall_b: float,
    compliance_a: float | None,
    compliance_b: float | None,
    preferred: Leader,
    threshold: float = MISMATCH_GAP_THRESHOLD,
) -> RewardMismatch:
    """Flag when rubric reward and hard-requirement compliance diverge.

    1. Per response: aggregate score exceeds compliance rate by >= threshold points.
    2. The preferred response satisfies fewer mandatory requirements than the other.
    3. The higher-scoring response satisfies fewer mandatory requirements than the other.
    """
    reasons: list[str] = []
    responses: dict[str, ResponseMismatch] = {}
    for label, overall, compliance in (("A", overall_a, compliance_a), ("B", overall_b, compliance_b)):
        gap = None if compliance is None else round(overall - compliance, 2)
        flagged = gap is not None and gap >= threshold
        if flagged:
            reasons.append(
                f"Response {label} scores {overall:.1f}% on the rubric but satisfies only "
                f"{compliance:.1f}% of mandatory requirements (gap {gap:.1f} points)."
            )
        responses[label] = ResponseMismatch(overall, compliance, gap, flagged)

    def less_compliant(label: str) -> bool:
        other = "B" if label == "A" else "A"
        mine, theirs = responses[label].compliance_rate, responses[other].compliance_rate
        return mine is not None and theirs is not None and mine < theirs

    preferred_less = preferred in ("A", "B") and less_compliant(preferred)
    if preferred_less:
        reasons.append(
            f"The preferred response ({preferred}) satisfies fewer mandatory requirements "
            "than the other response."
        )
    leader = score_leader(overall_a, overall_b)
    leader_less = leader in ("A", "B") and less_compliant(leader)
    if leader_less:
        reasons.append(
            f"The higher-scoring response ({leader}) satisfies fewer mandatory requirements "
            "than the other response."
        )
    return RewardMismatch(
        flagged=bool(reasons),
        threshold=threshold,
        responses=responses,
        preferred_less_compliant=preferred_less,
        score_leader_less_compliant=leader_less,
        reasons=reasons,
    )
