"""Read-only local API proof against independent accepted-preview literals."""
import argparse
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from s21_preview_inputs import AS_OF, EXPECTED, SOURCES, month_at

API = 'http://127.0.0.1:8210'
DATABASE = 's21_preview_ab7182f1866844428bd8b5c134bae80f'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify(manifest, artifact):
    require(manifest['database'] == manifest['tenant'] == DATABASE, 'Wrong private fixture target')
    require(manifest['as_of'] == AS_OF, 'Wrong preview reporting date')
    require(manifest['actor_email'] == 't19-preview-ab7182f1@example.test', 'Wrong fixture actor')
    physical = {source['key']: source for source in manifest['sources']}
    require(len(manifest['sources']) == len(physical) == 12, 'Expected exactly12 fixture sources')
    require(set(physical) == {source['id'] for source in SOURCES}, 'Fixture source keys changed')
    identities = {row.get('gm_model_id') or row['plan_id'] for row in physical.values()}
    require(len(identities) == 12, 'Physical source identity collision')
    account_ids = {account['id'] for account in manifest['accounts'].values()}
    require(len(account_ids) == 6, 'Expected six physical accounts')

    def get(scenario, quarters, account_id=None):
        params = dict(as_of=AS_OF, scenario=scenario, future_quarters=quarters)
        if account_id:
            params['account_id'] = account_id
        request = Request(API + '/forecast/outlook?' + urlencode(params),
                          headers={'X-Test-User': manifest['actor_email']}, method='GET')
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            require(response.status == 200, 'Forecast request failed')
        body = json.loads(raw, parse_float=Decimal)
        artifact['requests'].append(dict(params=params, response_sha256=sha256(raw).hexdigest(),
                                        watermark=body['source_watermark']))
        require(not body['excluded'] and not body['pending_sources'] and not body['unresolved_sources'],
                f'{params}: excluded/pending/unresolved sources')
        require(body['stale'] is False, f'{params}: stale result')
        require(body['currency'] == 'USD', 'Unexpected currency conversion')
        require(body['source_count'] == (2 if account_id else 12), 'Wrong source count')
        expected_ids = {key for key in identities if any(
            (row.get('gm_model_id') or row.get('plan_id')) == key and
            (not account_id or row['account_id'] == account_id) for row in physical.values())}
        require({row['source_id'] for row in body['rows']} == expected_ids, 'Physical source population changed')
        require({row['account_id'] for row in body['accounts']} == ({account_id} if account_id else account_ids),
                'Physical account population changed')
        return body

    for scenario in ('committed', 'expected', 'upside'):
        body = get(scenario, 4)
        require([row['start'] for row in body['months']] == list(EXPECTED['months']), '15-month date axis differs')
        require([Decimal(row['revenue']) for row in body['months']] == list(map(Decimal, EXPECTED[scenario])),
                f'{scenario}: monthly revenue differs')
        require([Decimal(row['revenue']) for row in body['quarters']] == list(map(Decimal, EXPECTED['quarters'][scenario])),
                f'{scenario}: five-quarter totals differ')
        require(Decimal(body['future']['revenue']) == Decimal(EXPECTED['future_four_quarters'][scenario]),
                f'{scenario}: four future quarters differ')
        require(Decimal(body['current_month']['revenue']) == Decimal('208500'), 'Current month differs')
        require(Decimal(body['current_quarter']['revenue']) == Decimal(EXPECTED['quarters'][scenario][0]),
                'Current quarter differs')
        for source in SOURCES:
            identity = physical[source['id']]
            sid = identity.get('gm_model_id') or identity['plan_id']
            rows = sorted((row for row in body['rows'] if row['source_id'] == sid), key=lambda row: row['month'])
            require(len(rows) == len(source['revenue']), f"{source['id']}: row count differs")
            weight = Decimal('1') if source['lifecycle'] == 'signed' or scenario == 'upside' else (
                Decimal(source['probability']) if scenario == 'expected' else Decimal('0'))
            for index, row in enumerate(rows):
                require(row['month'] == month_at(source['start'] + index).isoformat(), 'Source month differs')
                require(row['account_id'] == identity['account_id'], 'Source account differs')
                require(row['opportunity_id'] == identity['opportunity_id'], 'Source deal differs')
                require(row['source_version'] == (identity.get('sow_version_id') or identity['plan_version_id']),
                        'Source version differs')
                require(row['lifecycle'] == source['lifecycle'], 'Source lifecycle differs')
                require(Decimal(row['revenue']) == Decimal(source['revenue'][index]) * weight,
                        f"{scenario}/{source['id']}/{index}: literal revenue differs")
                require(row['cost'] is not None and Decimal(row['cost']) == Decimal(source['cost'][index]) * weight,
                        f"{scenario}/{source['id']}/{index}: literal cost differs")
        cx_signed = [row for row in body['rows'] if row['source_id'] == physical['cx-assess']['gm_model_id']]
        cx_plan = [row for row in body['rows'] if row['source_id'] == physical['cx-next']['plan_id']]
        require(sum((Decimal(row['signed']) for row in cx_signed), Decimal('0')) == Decimal('24000'),
                'Company X assessment signed value differs')
        require(all(Decimal(row['signed']) == 0 for row in cx_plan), 'Company X follow-on falsely signed')
        if scenario == 'upside':
            require(sum((Decimal(row['revenue']) for row in cx_plan), Decimal('0')) == Decimal('420000'),
                    'Company X follow-on not separately420000')
        short = get(scenario, 2)
        require(Decimal(short['future']['revenue']) == Decimal(EXPECTED['future'][scenario]),
                f'{scenario}: two future quarters differ')
        artifact['scenarios'][scenario] = dict(months=15, quarters=5, source_rows=len(body['rows']),
                                             next_two=short['future']['revenue'], next_four=body['future']['revenue'])
    for name, expected in EXPECTED['account_future_expected'].items():
        account = manifest['accounts'][name]
        body = get('expected', 2, account['id'])
        require(Decimal(body['future']['revenue']) == Decimal(expected), f'{name}: Expected future differs')
        artifact['accounts'][name] = dict(id=account['id'], future=body['future']['revenue'])
    artifact['sources'] = {key: {field: value for field, value in row.items()
                                if field.endswith('_id') or field in {'title', 'lifecycle'}}
                           for key, row in physical.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('/tmp/s21-preview-ab7182f1.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.manifest.resolve() == Path('/tmp/s21-preview-ab7182f1.json').resolve(), 'Exact source receipt required')
    require(args.output.parent.resolve() == Path('/tmp').resolve() and not args.output.is_symlink(),
            'Explicit new /tmp evidence path required')
    manifest = json.loads(args.manifest.read_text())
    artifact = dict(status='running', started_at=datetime.now(UTC).isoformat(), api=API, database=DATABASE,
                    boundary='Read-only local authenticated API; synthetic signed prerequisites, not live CRM/signature/staging proof',
                    requests=[], scenarios={}, accounts={})
    with args.output.open('x') as output:
        try:
            verify(manifest, artifact)
            artifact['status'] = 'passed'
        except Exception as error:
            artifact.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            artifact['finished_at'] = datetime.now(UTC).isoformat()
            json.dump(artifact, output, indent=2, sort_keys=True, default=str)
    print(json.dumps(dict(status='passed', output=str(args.output), requests=len(artifact['requests']),
                          sources=12, accounts=6, scenarios=3, months=15, quarters=5)))


if __name__ == '__main__':
    main()
