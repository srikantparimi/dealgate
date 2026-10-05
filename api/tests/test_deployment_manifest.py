"""Deployment gate checks actual bindings, never the latest family revision."""

from scripts.deployment_manifest import validate_manifest


IMAGE = "669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api:s21-sha"
DIGEST = "sha256:" + "a" * 64


def healthy():
    return {"services": [{"name": "api", "task_definition": "api:71", "desired": 1,
                          "running": 1, "pending": 0, "image": IMAGE,
                          "tasks": [{"task_definition": "api:71", "digest": DIGEST}]}],
            "schedules": [{"name": "sender", "state": "ENABLED", "target": "sender:6", "image": IMAGE}],
            "errors": []}


def test_pinned_old_worker_is_failure_even_if_latest_family_is_new():
    observed = healthy()
    observed["schedules"][0].update(target="sender:5", image="repo:old", latest_family_image=IMAGE)
    failures = validate_manifest(observed, expected_image=IMAGE, expected_digest=DIGEST,
                                 required_services={"api"}, required_schedules={"sender"})
    assert failures == ["sender: bound task image is repo:old, expected " + IMAGE]


def test_old_running_task_digest_fails_even_with_new_service_definition():
    observed = healthy()
    observed["services"][0]["tasks"][0]["digest"] = "sha256:old"
    failures = validate_manifest(observed, expected_image=IMAGE, expected_digest=DIGEST,
                                 required_services={"api"}, required_schedules={"sender"})
    assert "api: running task digest differs from release digest" in failures


def test_missing_continuous_consumer_or_read_error_is_not_empty_success():
    observed = healthy()
    observed["errors"] = ["AccessDenied: events targets"]
    failures = validate_manifest(observed, expected_image=IMAGE, expected_digest=DIGEST,
                                 required_services={"api", "consumer"}, required_schedules={"sender"})
    assert "Missing service: consumer" in failures
    assert "AccessDenied: events targets" in failures


def test_exact_healthy_bindings_pass():
    assert validate_manifest(healthy(), expected_image=IMAGE, expected_digest=DIGEST,
                             required_services={"api"}, required_schedules={"sender"}) == []
