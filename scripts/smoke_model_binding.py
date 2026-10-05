"""Read-only service-bound extraction model observation, using the AWS CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(),
             "Expected an explicit nonblank identity/value")
    return value


def _rows(value):
    _require(isinstance(value, list), "Expected a JSON list")
    return value


def _one(value):
    rows = _rows(value)
    _require(len(rows) == 1 and isinstance(rows[0], dict), "Expected exactly one description")
    return rows[0]


def _response(value):
    _require(isinstance(value, dict), "Expected a JSON object response")
    _require(not _rows(value.get("failures", [])), "AWS returned observation failures")
    _require(not value.get("nextToken") and not value.get("NextToken"), "Incomplete paginated observation")
    return value


def _arn(value, region, account=None):
    match = re.fullmatch(r"arn:(aws(?:-[a-z-]+)?):ecs:([^:]+):(\d{12}):(.+)", _text(value))
    _require(match is not None, "Expected a full ECS ARN")
    _require(match[2] == region and (account is None or match[3] == account),
             "ECS identity has the wrong region/account")
    return match[3], match[4]


def _service(response, *, cluster, service, region):
    row = _one(_response(response)["services"])
    _require(row["serviceName"] == service and row["status"] == "ACTIVE", "Wrong/inactive service")
    account, cluster_resource = _arn(row["clusterArn"], region)
    _require(cluster_resource.startswith("cluster/") and
             (row["clusterArn"] == cluster if cluster.startswith("arn:") else cluster_resource == f"cluster/{cluster}"),
             "Wrong service cluster")
    _, service_resource = _arn(row["serviceArn"], region, account)
    cluster_name = cluster_resource.split("/", 1)[1]
    _require(service_resource in (f"service/{service}", f"service/{cluster_name}/{service}"), "Wrong service ARN")
    _, definition_resource = _arn(row["taskDefinition"], region, account)
    _require(re.fullmatch(r"task-definition/[^/:]+:[1-9][0-9]*", definition_resource) is not None,
             "Service must bind a versioned task-definition ARN")
    for field, expected in (("desiredCount", 1), ("runningCount", 1), ("pendingCount", 0)):
        _require(type(row[field]) is int and row[field] == expected, "Service must have one converged running task")
    deployment = _one(row["deployments"])
    _require(deployment["status"] == "PRIMARY" and deployment["rolloutState"] == "COMPLETED"
             and deployment["taskDefinition"] == row["taskDefinition"], "Service rollout is not converged")
    return row


def _container(containers, name):
    rows = _rows(containers)
    _require(all(isinstance(row, dict) and isinstance(row.get("name"), str) for row in rows),
             "Malformed container descriptions")
    return _one([row for row in rows if row["name"] == name])


def collect_binding(aws, *, cluster, service, container, region):
    """Observe one converged task; never substitute a latest-family description."""
    try:
        service_args = ("ecs", "describe-services", "--cluster", cluster, "--services", service)
        tasks_args = ("ecs", "list-tasks", "--cluster", cluster, "--service-name", service,
                      "--desired-status", "RUNNING")
        observed = _service(aws(*service_args), cluster=cluster, service=service, region=region)
        definition_arn = observed["taskDefinition"]
        account, definition_resource = _arn(definition_arn, region)
        ids = _rows(_response(aws(*tasks_args))["taskArns"])
        _require(len(ids) == 1, "Expected exactly one running task ARN")
        task_arn = _text(ids[0])
        _, task_resource = _arn(task_arn, region, account)
        _require(task_resource.startswith("task/"), "Wrong task ARN")
        task = _one(_response(aws("ecs", "describe-tasks", "--cluster", cluster, "--tasks", task_arn))["tasks"])
        _require(task["taskArn"] == task_arn and task["clusterArn"] == observed["clusterArn"]
                 and task["group"] == f"service:{service}" and task["taskDefinitionArn"] == definition_arn,
                 "Running task does not match the service binding")
        _require(task["lastStatus"] == task["desiredStatus"] == "RUNNING", "Task is not running")
        definition = _response(aws("ecs", "describe-task-definition", "--task-definition", definition_arn))["taskDefinition"]
        family, revision = definition_resource.split("/", 1)[1].rsplit(":", 1)
        _require(definition["taskDefinitionArn"] == definition_arn and definition["status"] == "ACTIVE"
                 and definition["family"] == family and type(definition["revision"]) is int
                 and definition["revision"] == int(revision), "Wrong/inactive task-definition revision")
        defined = _container(definition["containerDefinitions"], container)
        running = _container(task["containers"], container)
        image = _text(defined["image"])
        _require(running["image"] == image and running["lastStatus"] == "RUNNING", "Wrong/nonrunning API container")
        digest = _text(running.get("imageDigest"))
        _require(re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None, "Missing/invalid running image digest")
        if "@sha256:" in image:
            _require(image.rsplit("@", 1)[1] == digest, "Pinned image digest conflicts with the running task")
        _require(not defined.get("environmentFiles"), "Environment-file model source is unresolved")
        secrets = _rows(defined.get("secrets", []))
        _require(all(isinstance(row, dict) and isinstance(row.get("name"), str)
                     and row["name"] not in {"SOW_EXTRACT_MODEL_ID", "SOW_EXTRACT_STUB", "DEALGATE_ENV"}
                     for row in secrets), "Secret-backed extraction setting is unresolved")
        environment = {}
        for entry in _rows(defined.get("environment", [])):
            name = _text(entry["name"])
            _require(name not in environment and isinstance(entry["value"], str), "Duplicate/invalid environment setting")
            environment[name] = entry["value"]
        model = _text(environment.get("SOW_EXTRACT_MODEL_ID"))
        _require(environment.get("SOW_EXTRACT_STUB") != "1" and environment.get("DEALGATE_ENV") not in ("local", "test"),
                 "Configured extraction runtime selects a stub")
        overrides = task.get("overrides", {})
        _require(isinstance(overrides, dict), "Malformed task overrides")
        for override in _rows(overrides.get("containerOverrides", [])):
            _require(isinstance(override, dict) and isinstance(override.get("name"), str), "Malformed container override")
            if override["name"] == container:
                _require(not override.get("environment") and not override.get("environmentFiles")
                         and not override.get("command"), "API container runtime override is unresolved")
        profiles = _rows(_response(aws("bedrock", "list-inference-profiles"))["inferenceProfileSummaries"])
        _require(all(isinstance(row, dict) and isinstance(row.get("inferenceProfileId"), str) for row in profiles),
                 "Malformed inference-profile descriptions")
        profile = _one([row for row in profiles if row["inferenceProfileId"] == model])
        _require(profile["status"] == "ACTIVE", "Configured inference profile is not active")
        after = _service(aws(*service_args), cluster=cluster, service=service, region=region)
        _require(after["taskDefinition"] == definition_arn and after["serviceArn"] == observed["serviceArn"]
                 and after["clusterArn"] == observed["clusterArn"], "Service changed during observation")
        _require(_response(aws(*tasks_args))["taskArns"] == ids, "Running tasks changed during observation")
        return {"observed_at": datetime.now(timezone.utc).isoformat(), "region": region,
                "cluster": observed["clusterArn"], "service": observed["serviceArn"], "container": container,
                "task_definition": definition_arn, "task": task_arn, "image": image,
                "digest": digest, "model_id": model, "profile_status": profile["status"]}
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Malformed AWS binding description") from exc


def aws_json(region, *args):
    command = ["aws", "--region", region, "--no-cli-pager", "--output", "json", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("AWS CLI observation could not complete") from exc
    _require(result.returncode == 0, f"AWS CLI {args[0]} {args[1]} failed")
    try:
        return _response(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise ValueError("AWS CLI returned invalid JSON") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("region", "cluster", "service", "container"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        result = collect_binding(lambda *command: aws_json(args.region, *command),
            cluster=args.cluster, service=args.service, container=args.container, region=args.region)
    except ValueError as exc:
        print(f"Model binding observation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
