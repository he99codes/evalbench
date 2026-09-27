"""Stage 1: parsing extraction output into requirement rows, plus the mock's extraction."""

import pytest

from app.models import RequirementType
from app.providers.base import LLMCallFailedError, LLMResponse
from app.providers.mock_provider import MockLLMProvider
from app.services import requirement_service
from app.utils.validation import RequirementExtractionOutput

REFUND_PROMPT = (
    'A customer named Jordan writes: "I was charged twice for order #4821 and I want my money back."\n\n'
    "Write a reply to Jordan. The reply must apologize for the double charge, confirm that the duplicate "
    "charge will be refunded to the original payment method, and offer a $10 store credit as a goodwill "
    "gesture. Keep the reply under 120 words. Do not promise a specific refund timeline or date. "
    "Use a friendly, professional tone."
)


def _item(type_, description, mandatory=True, source="src"):
    return {"type": type_, "description": description, "mandatory": mandatory, "source_text": source}


def test_parse_maps_buckets_and_coerces_types():
    output = RequirementExtractionOutput.model_validate(
        {
            "requests": [_item("REQUEST", "Apologize"), _item("FORMAT", "Offer credit")],
            "constraints": [_item("LENGTH", "Under 120 words"), _item("REQUEST", "No timeline")],
            "format_requirements": [_item("CONSTRAINT", "Use bullet points")],
            "ambiguities": ["Tone is subjective", "  ", "Tone is subjective"],
        }
    )
    rows, ambiguities = requirement_service.parse_extraction(output)
    types = {r.description: r.type for r in rows}
    assert types == {
        "Apologize": RequirementType.REQUEST,
        "Offer credit": RequirementType.REQUEST,  # FORMAT not allowed in requests -> default
        "Under 120 words": RequirementType.LENGTH,
        "No timeline": RequirementType.CONSTRAINT,  # REQUEST not allowed in constraints
        "Use bullet points": RequirementType.FORMAT,
    }
    assert ambiguities == ["Tone is subjective"]


def test_parse_dedupes_and_upgrades_mandatory():
    output = RequirementExtractionOutput.model_validate(
        {
            "requests": [_item("REQUEST", "Apologize to the customer.", mandatory=False)],
            "constraints": [_item("CONSTRAINT", "apologize to the customer", mandatory=True)],
            "format_requirements": [_item("FORMAT", "   ")],
            "ambiguities": [],
        }
    )
    rows, _ = requirement_service.parse_extraction(output)
    assert len(rows) == 1
    assert rows[0].mandatory is True and rows[0].type == RequirementType.REQUEST


def test_blank_source_text_becomes_none():
    output = RequirementExtractionOutput.model_validate(
        {"requests": [_item("REQUEST", "Do X", source="  ")], "constraints": [], "format_requirements": [], "ambiguities": []}
    )
    rows, _ = requirement_service.parse_extraction(output)
    assert rows[0].source_text is None


def test_mock_extracts_refund_requirements():
    extracted = requirement_service.extract_requirements(MockLLMProvider(), REFUND_PROMPT)
    by_type = {}
    for r in extracted.requirements:
        by_type.setdefault(r["type"], []).append(r["description"])
    assert "Keep the reply under 120 words." in by_type["LENGTH"]
    assert "Do not promise a specific refund timeline or date." in by_type["CONSTRAINT"]
    assert len(by_type["REQUEST"]) == 4  # write + apologize + confirm refund + offer credit
    # The quoted customer message is context, not a requirement.
    assert not any("money back" in d for ds in by_type.values() for d in ds)
    assert [r["ref"] for r in extracted.requirements] == [f"R{i}" for i in range(1, 8)]
    assert extracted.ambiguities  # tone is flagged as subjective


def test_mock_extraction_is_deterministic():
    a = requirement_service.extract_requirements(MockLLMProvider(), REFUND_PROMPT)
    b = requirement_service.extract_requirements(MockLLMProvider(), REFUND_PROMPT)
    strip = lambda reqs: [{k: v for k, v in r.items() if k != "id"} for r in reqs]  # noqa: E731
    assert strip(a.requirements) == strip(b.requirements)


class _MalformedProvider:
    name, model = "bad", "bad"

    def generate_structured(self, prompt, schema, *, system=None):
        return LLMResponse(data={"requests": "not-a-list"}, raw_text="{}")


def test_malformed_extraction_is_rejected_not_stored():
    from app.providers.base import RetryPolicy

    with pytest.raises(LLMCallFailedError):
        requirement_service.extract_requirements(
            _MalformedProvider(), "prompt", policy=RetryPolicy(max_attempts=2), sleep=lambda s: None
        )


def test_analyze_prompt_endpoint(client, api):
    project = api.create_project()
    c = api.create_criterion(project["id"])
    evaluation = api.create_evaluation(project["id"], [c], prompt=REFUND_PROMPT)
    r = client.post(f"/api/v1/evaluations/{evaluation['id']}/analyze-prompt")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "READY" and len(body["requirements"]) == 7 and body["ambiguities"]
    fetched = client.get(f"/api/v1/evaluations/{evaluation['id']}").json()
    assert fetched["status"] == "READY" and len(fetched["requirements"]) == 7
    # Re-analyzing replaces rather than duplicates.
    client.post(f"/api/v1/evaluations/{evaluation['id']}/analyze-prompt")
    assert len(client.get(f"/api/v1/evaluations/{evaluation['id']}").json()["requirements"]) == 7
    # Editing the prompt invalidates the requirements.
    r = client.patch(f"/api/v1/evaluations/{evaluation['id']}", json={"prompt": "Say hello."})
    assert r.json()["status"] == "DRAFT" and r.json()["requirements"] == []
