from copy import deepcopy

import pytest

from app.integrations.bedrock_sow_extract import StubBedrock, validate_extract
from app.services.direct_cost_proposals import propose_direct_costs
from app.services.document_text import text_document_from_string
from app.services.sow_extract import to_provenance_fields


def expense(**overrides):
    return {
        "category": "Travel", "note": "Client reimburses travel and expenses",
        "basis": "amount", "basis_value": None, "location": "proportional",
        "reimbursable": True, "page_ref": 4, **overrides,
    }


def fields_with(*lines):
    fields = deepcopy(StubBedrock().extract(text_document_from_string("SOW")).fields)
    fields["direct_costs"] = {"value": list(lines), "page_ref": 4, "status": "unconfirmed"}
    return fields


def test_unpriced_reimbursed_travel_is_a_proposal_not_a_zero_cost():
    extracted = validate_extract({"fields": fields_with(expense())})
    fields = to_provenance_fields(extracted.fields, model=extracted.model, prompt_version=extracted.prompt_version)
    assert fields["direct_costs"]["status"] == "unconfirmed"
    proposals = propose_direct_costs(fields)
    assert len(proposals) == 1
    assert proposals[0]["amount"] is None
    assert proposals[0]["basis_value"] is None
    assert proposals[0]["reimbursable"] is True
    assert proposals[0]["provenance"] == "extracted"
    assert proposals[0]["source_ref"] == "SOW p. 4"


def test_explicit_amount_and_percentage_are_normalized_without_computing():
    fields = fields_with(
        expense(basis_value="$2,300.25"),
        expense(category="Software/licenses", basis="percent_revenue", basis_value="2%", reimbursable=False),
    )
    proposals = propose_direct_costs(fields)
    assert proposals[0]["amount"] == "2300.25"
    assert proposals[1]["basis_value"] == "2"
    assert proposals[1]["amount"] is None


@pytest.mark.parametrize("change", [
    {"page_ref": 0}, {"reimbursable": "yes"}, {"basis_value": 2300.25},
    {"location": "unknown"}, {"extra": "invented"},
])
def test_malformed_expenses_are_rejected(change):
    with pytest.raises(ValueError):
        validate_extract({"fields": fields_with(expense(**change))})


def test_historical_extractions_remain_valid_and_have_no_proposals():
    extracted = StubBedrock().extract(text_document_from_string("SOW"))
    validate_extract({"fields": extracted.fields})
    assert propose_direct_costs(extracted.fields) == []


@pytest.mark.parametrize("value", ["NaN", "-50", "USD about 200", "Infinity"])
def test_non_amounts_do_not_become_money(value):
    proposals = propose_direct_costs(fields_with(expense(basis_value=value)))
    assert proposals[0]["amount"] is None
    assert proposals[0]["basis_value"] is None
