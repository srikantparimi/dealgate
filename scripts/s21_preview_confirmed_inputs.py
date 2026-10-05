"""Explicit synthetic confirmations for the accepted preview, never source extraction.

Pure helper: no database, API, storage, worker or provider operations.
"""
from copy import deepcopy

from s21_preview_inputs import preflight, records


CONFIRMATION = (
    'Synthetic fixture confirmation: Mon-Fri eight scheduled/billable/paid hours, '
    'no holidays, caller-declared location/timezone, and 4800 monthly cost per '
    'person at full allocation; not extraction or HR approval.'
)


def confirmed_records(*, location, timezone):
    """Return fresh complete inputs while preserving original source evidence."""
    result = deepcopy(records(location=location, timezone=timezone))
    for item in result:
        if item['id'] not in {'atlas-staff', 'atlas-extend'}:
            continue
        inputs = item['inputs']
        # Fail closed if source facts change: never clear unrelated cost lines.
        if (len(inputs['costs']) != 6 or any(row['amount'] != '28800' for row in inputs['costs'])
                or len(inputs['staffing']) != 1):
            raise ValueError('Atlas preview cost evidence changed; review fixture confirmation')
        staffing = inputs['staffing'][0]
        if staffing['quantity'] != 6 or staffing['allocation'] != '1':
            raise ValueError('Atlas preview staffing changed; review fixture confirmation')
        staffing.update(
            cost_rate='4800', cost_version='synthetic-preview-monthly-cost-v1',
            cost_rate_basis='monthly', cost_proration=None,
            calendar=dict(
                calendar_id=f"synthetic-preview-{item['id']}-{location}",
                version='synthetic-preview-calendar-v1', timezone=timezone,
                coverage_start='2026-01-01', coverage_end='2028-12-31',
                week=[dict(scheduled=hours, billable=hours, paid=hours)
                      for hours in ('8', '8', '8', '8', '8', '0', '0')],
                overrides=[],
            ),
        )
        inputs['costs'] = []
        inputs['cost_basis'] = CONFIRMATION
        inputs['source_evidence'].append(CONFIRMATION)
        item['fixture_assumptions'].append(CONFIRMATION)
        item['source_unknowns'] = item['unknowns']
        item['unknowns'] = []
    preflight(result)
    return result
