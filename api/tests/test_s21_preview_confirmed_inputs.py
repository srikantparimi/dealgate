from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from s21_preview_inputs import EXPECTED, SOURCES, preflight, records
from s21_preview_confirmed_inputs import confirmed_records
from app.gm.commercial import calculate_component
from app.services.commercial_models import parse_component


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_twelve_complete_records_match_all_independent_monthly_money():
    items = confirmed_records(location='US', timezone='America/New_York')
    assert preflight(items) == {'sources': 12, 'accounts': 6, 'complete': True}
    for item in items:
        rows = calculate_component(parse_component(item['inputs'])).rows
        assert [row.revenue for row in rows] == list(map(Decimal, item['revenue']))
        assert [row.cost for row in rows] == list(map(Decimal, item['cost']))
        if item['id'].startswith('atlas-'):
            assert item['profile'] == 'calendar_staff_aug'
            assert len(rows) == 6
            assert [row.revenue for row in rows] == [Decimal('48000')] * 6
            assert [row.cost for row in rows] == [Decimal('28800')] * 6
            assert item['inputs']['costs'] == []


def test_original_unconfirmed_inputs_and_source_oracles_are_immutable():
    original = records(location='US', timezone='America/New_York')
    digest = fingerprint(original)
    source_digest = fingerprint(SOURCES)
    expected_digest = fingerprint(EXPECTED)
    confirmed = confirmed_records(location='US', timezone='America/New_York')
    assert fingerprint(original) == digest
    assert fingerprint(records(location='US', timezone='America/New_York')) == digest
    assert fingerprint(SOURCES) == source_digest
    assert fingerprint(EXPECTED) == expected_digest
    with pytest.raises(ValueError) as error:
        preflight(original)
    assert [row['id'] for row in error.value.args[0]] == ['atlas-staff', 'atlas-extend']
    for before, after in zip(original, confirmed, strict=True):
        for key in ('id', 'client', 'title', 'source', 'evidence', 'probability', 'lifecycle', 'preview_lifecycle', 'revenue', 'cost'):
            assert after[key] == before[key]
        if not before['id'].startswith('atlas-'):
            assert after == before
        else:
            assert after['inputs']['source_evidence'][:2] == before['inputs']['source_evidence']
            assert after['source_unknowns'] == before['unknowns']
    preserved = deepcopy(confirmed[3]['inputs']['staffing'][0]['calendar'])
    confirmed[9]['inputs']['staffing'][0]['calendar']['week'][0]['paid'] = '1'
    assert confirmed[3]['inputs']['staffing'][0]['calendar'] == preserved


@pytest.mark.parametrize('location,timezone', [('US', 'America/New_York'), ('India', 'Asia/Kolkata')])
def test_explicit_versioned_calendar_and_fixture_authority(location, timezone):
    items = confirmed_records(location=location, timezone=timezone)
    preflight(items)
    for item in items:
        if not item['id'].startswith('atlas-'):
            continue
        staffing = item['inputs']['staffing'][0]
        assert staffing['location'] == location
        assert staffing['timezone'] == timezone
        assert staffing['quantity'] == 6
        assert staffing['allocation'] == '1'
        assert staffing['cost_rate'] == '4800'
        assert staffing['cost_rate_basis'] == 'monthly'
        assert staffing['cost_proration'] is None
        assert staffing['cost_version'] == 'synthetic-preview-monthly-cost-v1'
        calendar = staffing['calendar']
        assert calendar['timezone'] == timezone
        assert calendar['coverage_start'] == '2026-01-01'
        assert calendar['coverage_end'] == '2028-12-31'
        assert calendar['version'] == 'synthetic-preview-calendar-v1'
        assert calendar['overrides'] == []
        assert calendar['week'] == [{'scheduled': '8', 'billable': '8', 'paid': '8'}] * 5 + [{'scheduled': '0', 'billable': '0', 'paid': '0'}] * 2
        assert 'not extraction or HR approval' in item['inputs']['cost_basis']
        assert item['unknowns'] == []


@pytest.mark.parametrize('location,timezone', [('EU', 'Europe/Paris'), ('US', '')])
def test_unconfirmed_fixture_geography_rejected(location, timezone):
    with pytest.raises(ValueError):
        confirmed_records(location=location, timezone=timezone)
