"""S24-AG1 T11 — the leak gate (scripts/check-test-data-clean.sh) on stubs.

Runs the REAL gate script with stub ``aws`` and ``curl`` first on PATH: canned JSON per scenario, no network
and no AWS credentials in the environment. It checks that the gate fails on a leaked "S23 e2e"/"S24 e2e" client
and on a test upload under ``agreements/e2e/`` older than the grace period, prints a younger one as pending
cleanup, exits 2 when it cannot list the bucket, and only ever makes four read-only AWS calls. Ported from the
T-A lane's scratch harness so the proof lives in the repo (verifier finding).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

GATE = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-test-data-clean.sh"
BASH = shutil.which("bash")
PYTHON3 = shutil.which("python3")
pytestmark = pytest.mark.skipif(not (BASH and PYTHON3), reason="needs bash and python3")

AWS_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
printf 'aws %s\n' "$*" >> "$STUB_LOG"
args=" $* "
case "$args" in
  *" secretsmanager get-secret-value "*)
    printf '%s\n' '{"user_pool_id":"us-east-2_STUB","client_id":"stub-client","username":"stub-bot","password":"stub-fake"}' ;;
  *" cognito-idp admin-initiate-auth "*)
    printf '%s\n' '{"AuthenticationResult":{"IdToken":"stub-fake-id-token"}}' ;;
  *" sts get-caller-identity "*)
    printf '%s\n' "123456789012" ;;
  *" s3api list-objects-v2 "*)
    if [ -f "$SCENARIO/s3_fail" ]; then echo "AccessDenied (stub)" >&2; exit 254; fi
    cat "$SCENARIO/objects.json" ;;
  *) echo "aws stub: unexpected call: $*" >&2; exit 97 ;;
esac
"""

CURL_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
url="${*: -1}"
printf 'curl %s\n' "$url" >> "$STUB_LOG"
case "$url" in
  */api/clients\?size=200) cat "$SCENARIO/clients.json" ;;
  */api/approvals/packages*) printf '%s\n' '{"items":[]}' ;;
  */api/resources) printf '%s\n' '[]' ;;
  */api/engagements*) printf '%s\n' '{"items":[]}' ;;
  */api/me) printf '%s\n' '{"id":"stub-bot-id"}' ;;
  */api/pipeline/views|*/api/pipeline/groups|*/api/saved-views|*/api/tracking-groups|*/api/watchlist)
    printf '%s\n' '[]' ;;
  *) echo "curl stub: unexpected url: $url" >&2; exit 97 ;;
esac
"""

REAL_CLIENTS = ('{"items":[{"id":"c-1","name":"Atlas Foods"},{"id":"c-2","name":"Beacon Logistics"},'
                '{"id":"c-3","name":"S24 Engineering Group"}]}')
RUN = "7c0d6a52-6a54-4d3b-9e0e-2f4f1d1f3a11"
AGR = "0f8e2b7c-4c1d-4a2e-8f6b-5a9d3c2e1b00"
OLD_KEY = f"agreements/e2e/{RUN}/{AGR}/20261015T100000Z-0a1b2c3d-run nda.pdf"
YOUNG_KEY = f"agreements/e2e/{RUN}/{AGR}/20261015T190000Z-4e5f6a7b-run msa.pdf"
READ_ONLY = ("secretsmanager get-secret-value", "cognito-idp admin-initiate-auth", "sts get-caller-identity",
             "s3api list-objects-v2")


def ago(minutes: float, *, v1: bool = False) -> str:
    """An S3 LastModified for N minutes ago, in the AWS CLI v2 style or (v1) with milliseconds and Z."""
    t = datetime.now(UTC) - timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z") if v1 else t.replace(microsecond=0).isoformat()


def objects(*items: tuple[str, str]) -> str:
    import json

    return json.dumps({"Contents": [{"Key": key, "LastModified": stamp, "Size": 72} for key, stamp in items],
                      "KeyCount": len(items)})


@pytest.fixture
def stubs(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("aws", AWS_STUB), ("curl", CURL_STUB)):
        path = bin_dir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def run_gate(tmp_path, stubs, clients: str, listing: str, *, s3_fail: bool = False, **extra: str):
    scenario = tmp_path / "scenario"
    scenario.mkdir(exist_ok=True)
    (scenario / "clients.json").write_text(clients)
    (scenario / "objects.json").write_text(listing)
    if s3_fail:
        (scenario / "s3_fail").touch()
    log = scenario / "calls.log"
    log.write_text("")
    env = {
        "HOME": str(tmp_path), "PATH": f"{stubs}:{os.path.dirname(PYTHON3)}:/usr/bin:/bin",
        "SCENARIO": str(scenario), "STUB_LOG": str(log), "BASE_URL": "https://gate-stub.invalid",
        "AWS_REGION": "us-east-2", "E2E_SECRET_ID": "stub-secret", "AWS_CONFIG_FILE": "/dev/null",
        "AWS_SHARED_CREDENTIALS_FILE": "/dev/null", **extra,
    }
    done = subprocess.run([BASH, str(GATE)], env=env, capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout, done.stderr, log.read_text()


def aws_calls_are_read_only(log: str) -> bool:
    calls = [line for line in log.splitlines() if line.startswith("aws ")]
    return bool(calls) and all(any(f" {op} " in f"{line} " for op in READ_ONLY) for line in calls)


def test_the_gate_parses():
    assert subprocess.run([BASH, "-n", str(GATE)], capture_output=True).returncode == 0


def test_clean_lists_exactly_the_e2e_prefix_of_the_default_bucket(tmp_path, stubs):
    code, out, _err, log = run_gate(tmp_path, stubs, REAL_CLIENTS, '{"KeyCount": 0, "Prefix": "agreements/e2e/"}')
    assert code == 0, out
    assert "[gate] clean" in out and "pending cleanup" not in out
    assert "s3://officeapp-dev-agreements-123456789012/agreements/e2e/" in out
    assert "s3api list-objects-v2 --bucket officeapp-dev-agreements-123456789012 --prefix agreements/e2e/" in log
    assert aws_calls_are_read_only(log)


def test_an_empty_listing_body_is_clean(tmp_path, stubs):
    code, out, _err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS, "")
    assert code == 0, out


@pytest.mark.parametrize(("client_id", "name"), [("c-24", "S24 e2e 1760563200000 Agreements fixture"),
                                                 ("c-23", "S23 e2e 1760000000000 Pipeline")])
def test_a_leaked_s23_or_s24_client_fails_the_gate(tmp_path, stubs, client_id, name):
    clients = ('{"items":[{"id":"c-1","name":"Atlas Foods"},{"id":"c-3","name":"S24 Engineering Group"},'
               f'{{"id":"{client_id}","name":"{name}"}}]}}')
    code, _out, err, _log = run_gate(tmp_path, stubs, clients, '{"KeyCount": 0}')
    assert code == 1
    assert f"LEAK\t{client_id}\t{name}" in err
    assert "S24 Engineering Group" not in err  # a real name that merely starts with S24 is not a run tag


def test_an_old_test_upload_fails_and_is_printed(tmp_path, stubs):
    code, _out, err, log = run_gate(tmp_path, stubs, REAL_CLIENTS, objects((OLD_KEY, ago(120))))
    assert code == 1
    assert "+ 1 test uploads older than 30 min in s3://officeapp-dev-agreements-123456789012/agreements/e2e/" in err
    assert f"AGREEMENT-LEAK\t{OLD_KEY}" in err and "120 min old" in err
    assert aws_calls_are_read_only(log)


def test_a_young_test_upload_is_pending_cleanup_not_a_failure(tmp_path, stubs):
    code, out, _err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS, objects((YOUNG_KEY, ago(5))))
    assert code == 0
    assert "[gate] clean" in out and "[gate] pending cleanup" in out
    assert f"AGREEMENT-PENDING\t{YOUNG_KEY}" in out and "min old, pending cleanup" in out


def test_old_and_young_uploads_fail_and_print_both(tmp_path, stubs):
    code, _out, err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS, objects((OLD_KEY, ago(45)), (YOUNG_KEY, ago(2))))
    assert code == 1
    assert f"AGREEMENT-LEAK\t{OLD_KEY}" in err and f"AGREEMENT-PENDING\t{YOUNG_KEY}" in err
    assert "+ 1 test uploads older than 30 min" in err


def test_cli_v1_times_count_and_an_unreadable_time_is_reported(tmp_path, stubs):
    odd = "agreements/e2e/x/y/z.pdf"
    code, _out, err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS,
                                     objects((OLD_KEY, ago(31, v1=True)), (odd, "yesterday")))
    assert code == 1
    assert f"AGREEMENT-LEAK\t{OLD_KEY}" in err
    assert f"AGREEMENT-LEAK\t{odd}\tyesterday\tage unknown" in err


def test_a_bucket_that_cannot_be_listed_exits_2(tmp_path, stubs):
    code, _out, err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS, "", s3_fail=True)
    assert code == 2
    assert "[gate] cannot list s3://officeapp-dev-agreements-123456789012/agreements/e2e/" in err


def test_agreements_bucket_overrides_the_default_without_an_account_lookup(tmp_path, stubs):
    code, out, _err, log = run_gate(tmp_path, stubs, REAL_CLIENTS, '{"KeyCount": 0}',
                                    AGREEMENTS_BUCKET="stub-agreements-bucket")
    assert code == 0, out
    assert "s3api list-objects-v2 --bucket stub-agreements-bucket --prefix agreements/e2e/" in log
    assert "sts get-caller-identity" not in log
    assert "s3://stub-agreements-bucket/agreements/e2e/" in out


def test_a_custom_grace_period(tmp_path, stubs):
    code, _out, err, _log = run_gate(tmp_path, stubs, REAL_CLIENTS, objects((YOUNG_KEY, ago(20))),
                                     AGREEMENTS_GRACE_MINUTES="10")
    assert code == 1
    assert f"AGREEMENT-LEAK\t{YOUNG_KEY}" in err
