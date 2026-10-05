"""Offline CLI observation contracts, not mocked extraction outcome proof."""

import copy
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "arn:aws:ecs:us-east-2:123456789012:"
CLUSTER = PREFIX + "cluster/officeapp-dev-cluster"
DEFINITION = PREFIX + "task-definition/officeapp-dev-api:70"
TASK = PREFIX + "task/officeapp-dev-cluster/task-one"
IMAGE = "123456789012.dkr.ecr.us-east-2.amazonaws.com/api:immutable"
MODEL = "us.anthropic.claude-sonnet-4-6"
DIGEST = "sha256:" + "a" * 64


def observations():
    return {
        "describe-services": {"services": [{"serviceName": "officeapp-dev-api",
            "serviceArn": PREFIX + "service/officeapp-dev-cluster/officeapp-dev-api",
            "clusterArn": CLUSTER, "status": "ACTIVE", "taskDefinition": DEFINITION,
            "desiredCount": 1, "runningCount": 1, "pendingCount": 0,
            "deployments": [{"status": "PRIMARY", "taskDefinition": DEFINITION,
                "rolloutState": "COMPLETED"}]}], "failures": []},
        "list-tasks": {"taskArns": [TASK]},
        "describe-tasks": {"tasks": [{"taskArn": TASK, "clusterArn": CLUSTER,
            "group": "service:officeapp-dev-api", "taskDefinitionArn": DEFINITION,
            "lastStatus": "RUNNING", "desiredStatus": "RUNNING", "overrides": {},
            "containers": [{"name": "api", "image": IMAGE, "imageDigest": DIGEST,
                "lastStatus": "RUNNING"}]}], "failures": []},
        "describe-task-definition": {"taskDefinition": {"taskDefinitionArn": DEFINITION,
            "family": "officeapp-dev-api", "revision": 70, "status": "ACTIVE",
            "containerDefinitions": [{"name": "api", "image": IMAGE,
                "environment": [{"name": "SOW_EXTRACT_MODEL_ID", "value": MODEL}]}]}},
        "list-inference-profiles": {"inferenceProfileSummaries": [
            {"inferenceProfileId": MODEL, "status": "ACTIVE"}]},
    }


def execute(data, *, after=None):
    from scripts.smoke_model_binding import collect_binding
    calls = []

    def aws(*args):
        calls.append(args)
        if args[1] == "describe-services" and after and sum(c[1] == args[1] for c in calls) > 1:
            return copy.deepcopy(after)
        return copy.deepcopy(data[args[1]])

    result = collect_binding(aws, cluster="officeapp-dev-cluster",
        service="officeapp-dev-api", container="api", region="us-east-2")
    return result, calls


def test_observes_exact_service_revision_not_latest_family():
    result, calls = execute(observations())
    assert result["task_definition"] == DEFINITION
    assert result["task"] == TASK and result["digest"] == DIGEST
    assert result["model_id"] == MODEL and result["image"] == IMAGE
    assert ("ecs", "describe-task-definition", "--task-definition", DEFINITION) in calls
    assert sum(call[1] == "describe-services" for call in calls) == 2
    assert all("officeapp-dev-api:71" not in call for call in calls)


@pytest.mark.parametrize("case", [
    "missing_service", "multiple_service", "wrong_service", "wrong_cluster", "failed_service",
    "zero_desired", "multiple_running", "pending", "rolling", "multiple_deployments",
    "unversioned_definition", "no_tasks", "duplicate_tasks", "multiple_tasks", "incomplete_tasks",
    "missing_task", "wrong_task", "wrong_task_cluster", "wrong_group", "old_task_revision",
    "stopped", "stopped_container", "no_digest", "bad_digest", "wrong_image", "failed_tasks",
    "wrong_definition", "wrong_revision", "inactive_definition", "missing_container",
    "duplicate_container", "duplicate_running_container", "no_model", "duplicate_model",
    "blank_model", "model_secret", "environment_file", "override", "profile_missing",
    "profile_duplicate", "profile_inactive", "profile_incomplete", "malformed_services",
])
def test_invalid_or_ambiguous_observations_fail_closed(case):
    data = observations()
    svc = data["describe-services"]["services"][0]
    task = data["describe-tasks"]["tasks"][0]
    definition = data["describe-task-definition"]["taskDefinition"]
    container = definition["containerDefinitions"][0]
    profiles = data["list-inference-profiles"]
    if case == "missing_service": data["describe-services"]["services"] = []
    elif case == "multiple_service": data["describe-services"]["services"].append(copy.deepcopy(svc))
    elif case == "wrong_service": svc["serviceName"] = "other"
    elif case == "wrong_cluster": svc["clusterArn"] = PREFIX + "cluster/other"
    elif case == "failed_service": data["describe-services"]["failures"] = [{"reason": "MISSING"}]
    elif case == "zero_desired": svc["desiredCount"] = 0
    elif case == "multiple_running": svc["runningCount"] = 2
    elif case == "pending": svc["pendingCount"] = 1
    elif case == "rolling": svc["deployments"][0]["rolloutState"] = "IN_PROGRESS"
    elif case == "multiple_deployments": svc["deployments"].append(copy.deepcopy(svc["deployments"][0]))
    elif case == "unversioned_definition": svc["taskDefinition"] = "officeapp-dev-api"
    elif case == "no_tasks": data["list-tasks"]["taskArns"] = []
    elif case == "duplicate_tasks": data["list-tasks"]["taskArns"] *= 2
    elif case == "multiple_tasks": data["list-tasks"]["taskArns"].append(TASK + "2")
    elif case == "incomplete_tasks": data["list-tasks"]["nextToken"] = "more"
    elif case == "missing_task": data["describe-tasks"]["tasks"] = []
    elif case == "wrong_task": task["taskArn"] += "other"
    elif case == "wrong_task_cluster": task["clusterArn"] = PREFIX + "cluster/other"
    elif case == "wrong_group": task["group"] = "service:other"
    elif case == "old_task_revision": task["taskDefinitionArn"] = DEFINITION[:-2] + "69"
    elif case == "stopped": task["lastStatus"] = "STOPPED"
    elif case == "stopped_container": task["containers"][0]["lastStatus"] = "STOPPED"
    elif case == "no_digest": task["containers"][0].pop("imageDigest")
    elif case == "bad_digest": task["containers"][0]["imageDigest"] = "latest"
    elif case == "wrong_image": task["containers"][0]["image"] = IMAGE + "-other"
    elif case == "failed_tasks": data["describe-tasks"]["failures"] = [{"reason": "MISSING"}]
    elif case == "wrong_definition": definition["taskDefinitionArn"] = DEFINITION[:-2] + "71"
    elif case == "wrong_revision": definition["revision"] = 71
    elif case == "inactive_definition": definition["status"] = "INACTIVE"
    elif case == "missing_container": definition["containerDefinitions"] = [{"name": "sidecar"}]
    elif case == "duplicate_container": definition["containerDefinitions"].append(copy.deepcopy(container))
    elif case == "duplicate_running_container": task["containers"] *= 2
    elif case == "no_model": container["environment"] = []
    elif case == "duplicate_model": container["environment"] *= 2
    elif case == "blank_model": container["environment"][0]["value"] = " "
    elif case == "model_secret": container["secrets"] = [{"name": "SOW_EXTRACT_MODEL_ID", "valueFrom": "secret"}]
    elif case == "environment_file": container["environmentFiles"] = [{"value": "s3://env"}]
    elif case == "override": task["overrides"] = {"containerOverrides": [{"name": "api", "environment": [{"name": "SOW_EXTRACT_MODEL_ID", "value": "other"}]}]}
    elif case == "profile_missing": profiles["inferenceProfileSummaries"] = []
    elif case == "profile_duplicate": profiles["inferenceProfileSummaries"] *= 2
    elif case == "profile_inactive": profiles["inferenceProfileSummaries"][0]["status"] = "INACTIVE"
    elif case == "profile_incomplete": profiles["nextToken"] = "more"
    elif case == "malformed_services": data["describe-services"]["services"] = {}
    with pytest.raises(ValueError):
        execute(data)


def test_service_changes_during_observation_fail_closed():
    data = observations()
    after = copy.deepcopy(data["describe-services"])
    after["services"][0]["taskDefinition"] = DEFINITION[:-2] + "71"
    with pytest.raises(ValueError):
        execute(data, after=after)


@pytest.mark.parametrize("setting,value", [("SOW_EXTRACT_STUB", "1"), ("DEALGATE_ENV", "local"), ("DEALGATE_ENV", "test")])
def test_explicit_stub_runtime_cannot_be_model_invocation_evidence(setting, value):
    data = observations()
    data["describe-task-definition"]["taskDefinition"]["containerDefinitions"][0]["environment"].append({"name": setting, "value": value})
    with pytest.raises(ValueError):
        execute(data)


@pytest.mark.parametrize("name", ["SOW_EXTRACT_STUB", "DEALGATE_ENV"])
def test_secret_backed_extraction_selector_is_unresolved(name):
    data = observations()
    data["describe-task-definition"]["taskDefinition"]["containerDefinitions"][0]["secrets"] = [
        {"name": name, "valueFrom": "secret"}]
    with pytest.raises(ValueError):
        execute(data)


def test_named_container_selection_never_uses_first_sidecar():
    data = observations()
    data["describe-task-definition"]["taskDefinition"]["containerDefinitions"].insert(0, {"name": "sidecar", "image": "irrelevant"})
    data["describe-tasks"]["tasks"][0]["containers"].insert(0, {"name": "sidecar", "image": "irrelevant"})
    assert execute(data)[0]["model_id"] == MODEL


def test_cli_json_errors_and_nonzero_exit_fail_closed(monkeypatch):
    from scripts.smoke_model_binding import aws_json
    from subprocess import CompletedProcess
    seen = []

    def run(command, **kwargs):
        seen.append(command)
        return CompletedProcess(command, 0, "not JSON", "")

    monkeypatch.setattr("scripts.smoke_model_binding.subprocess.run", run)
    with pytest.raises(ValueError):
        aws_json("eu-west-1", "ecs", "describe-services")
    assert seen[0][:4] == ["aws", "--region", "eu-west-1", "--no-cli-pager"]
    monkeypatch.setattr("scripts.smoke_model_binding.subprocess.run",
        lambda command, **kwargs: CompletedProcess(command, 1, json.dumps(observations()), "denied"))
    with pytest.raises(ValueError):
        aws_json("eu-west-1", "ecs", "describe-services")


def test_smoke_guard_calls_helper_and_does_not_query_latest_family():
    script = (ROOT / "scripts/deploy-smoke.sh").read_text()
    step = script.split("# ---- Step 2:")[1].split("# ---- Step 3:")[0]
    assert "smoke_model_binding.py" in step
    assert "--task-definition officeapp-dev-api" not in step
    assert '--region "$AWS_REGION_"' in step


def test_deploy_smoke_uses_server_issued_fixture_and_bound_upload():
    """The e2e identity may only read records in its issued fixture scope."""

    script = (ROOT / "scripts/deploy-smoke.sh").read_text()
    assert '"$BASE_URL/api/dev/test-fixtures"' in script
    assert '-F "client_id=$CLIENT_ID_TO_DELETE"' in script
    assert '-F "opportunity_id=$FIXTURE_OPP_ID"' in script
    assert '"$BASE_URL/api/sows/jobs/$JOB_ID/pick"' not in script
