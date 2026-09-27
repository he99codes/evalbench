import math

import pytest

from app.utils.scoring import (
    CriterionWeight,
    ScoringError,
    aggregate_score,
    compliance_rate,
    detect_reward_mismatch,
    normalize,
    normalized_weights,
    score_leader,
)

W = [
    CriterionWeight("acc", 2.0, 1, 5),
    CriterionWeight("tone", 1.0, 1, 5),
    CriterionWeight("fmt", 1.0, 0, 10),
]


def test_normalize():
    assert normalize(1, 1, 5) == 0
    assert normalize(5, 1, 5) == 1
    assert normalize(3, 1, 5) == 0.5
    with pytest.raises(ScoringError):
        normalize(6, 1, 5)
    with pytest.raises(ScoringError):
        normalize(3, 5, 5)
    with pytest.raises(ScoringError):
        normalize(math.nan, 1, 5)


def test_weighted_aggregate():
    # acc 1.0 * 0.5 + tone 0.5 * 0.25 + fmt 0.2 * 0.25 = 0.675
    assert aggregate_score(W, {"acc": 5, "tone": 3, "fmt": 2}) == 67.5
    assert aggregate_score(W, {"acc": 1, "tone": 1, "fmt": 0}) == 0
    assert aggregate_score(W, {"acc": 5, "tone": 5, "fmt": 10}) == 100


def test_weights_are_relative():
    doubled = [CriterionWeight(w.criterion_id, w.weight * 2, w.scale_min, w.scale_max) for w in W]
    scores = {"acc": 4, "tone": 2, "fmt": 7}
    assert aggregate_score(W, scores) == aggregate_score(doubled, scores)


def test_missing_criterion_raises():
    with pytest.raises(ScoringError, match="missing score"):
        aggregate_score(W, {"acc": 5, "tone": 3})


def test_zero_weight_criterion_may_be_missing_and_is_ignored():
    weights = [CriterionWeight("a", 1, 1, 5), CriterionWeight("b", 0, 1, 5)]
    assert aggregate_score(weights, {"a": 5}) == 100
    assert aggregate_score(weights, {"a": 5, "b": 1}) == 100


@pytest.mark.parametrize("bad", [-1.0, math.inf, math.nan])
def test_invalid_weight_raises(bad):
    with pytest.raises(ScoringError, match="invalid weight"):
        aggregate_score([CriterionWeight("a", bad, 1, 5)], {"a": 3})


def test_all_zero_or_empty_weights_raise():
    with pytest.raises(ScoringError):
        normalized_weights([CriterionWeight("a", 0, 1, 5)])
    with pytest.raises(ScoringError):
        normalized_weights([])


def test_unknown_or_out_of_scale_scores_raise():
    with pytest.raises(ScoringError, match="unknown"):
        aggregate_score(W, {"acc": 5, "tone": 3, "fmt": 2, "other": 1})
    with pytest.raises(ScoringError, match="outside scale"):
        aggregate_score(W, {"acc": 7, "tone": 3, "fmt": 2})


def test_tie_and_leader():
    assert score_leader(80.0, 80.0) == "TIE"
    assert score_leader(80.0, 80.4) == "TIE"  # within margin
    assert score_leader(80.0, 81.0) == "B"
    assert score_leader(90.0, 10.0) == "A"
    equal = {"acc": 3, "tone": 3, "fmt": 5}
    assert score_leader(aggregate_score(W, equal), aggregate_score(W, dict(equal))) == "TIE"


def test_compliance_rate():
    assert compliance_rate([]) is None
    assert compliance_rate([True, True, False]) == 66.67
    assert compliance_rate([True]) == 100


def test_reward_mismatch_gap_flag():
    result = detect_reward_mismatch(
        overall_a=88.0, overall_b=90.0, compliance_a=66.67, compliance_b=100.0, preferred="B"
    )
    assert result.flagged
    assert result.responses["A"].flagged and result.responses["A"].gap == 21.33
    assert not result.responses["B"].flagged
    assert "Response A" in result.reasons[0]


def test_reward_mismatch_preferred_and_leader_less_compliant():
    result = detect_reward_mismatch(
        overall_a=80.0, overall_b=70.0, compliance_a=75.0, compliance_b=100.0, preferred="A"
    )
    assert result.flagged
    assert result.preferred_less_compliant and result.score_leader_less_compliant
    assert not result.responses["A"].flagged  # gap 5 < threshold


def test_no_mismatch_when_aligned_or_no_requirements():
    aligned = detect_reward_mismatch(
        overall_a=95.0, overall_b=60.0, compliance_a=100.0, compliance_b=50.0, preferred="A"
    )
    assert not aligned.flagged and aligned.reasons == []
    empty = detect_reward_mismatch(
        overall_a=95.0, overall_b=60.0, compliance_a=None, compliance_b=None, preferred="TIE"
    )
    assert not empty.flagged and empty.responses["A"].gap is None
