"""Read-only ECS/EventBridge release binding gate; never mutates infrastructure."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def validate_manifest(manifest, *, expected_image, expected_digest, required_services, required_schedules):
    failures = list(manifest["errors"])
    services = {row["name"]: row for row in manifest["services"]}
    schedules = {row["name"]: row for row in manifest["schedules"]}
    failures += [f"Missing service: {name}" for name in sorted(required_services - services.keys())]
    failures += [f"Missing schedule: {name}" for name in sorted(required_schedules - schedules.keys())]
    for name in sorted(required_services & services.keys()):
        row = services[name]
        if row["image"] != expected_image:
            failures.append(f"{name}: bound task image is {row['image']}, expected {expected_image}")
        if row["desired"] < 1 or row["running"] != row["desired"] or row["pending"]:
            failures.append(f"{name}: service is not converged with at least one running task")
        if len(row["tasks"]) != row["desired"]:
            failures.append(f"{name}: observed running task count differs from desired")
        for task in row["tasks"]:
            if task["task_definition"] != row["task_definition"]:
                failures.append(f"{name}: running task definition differs from service binding")
            if task["digest"] != expected_digest:
                failures.append(f"{name}: running task digest differs from release digest")
    for name in sorted(required_schedules & schedules.keys()):
        row = schedules[name]
        if row["state"] != "ENABLED":
            failures.append(f"{name}: schedule is not enabled")
        if row["image"] != expected_image:
            failures.append(f"{name}: bound task image is {row['image']}, expected {expected_image}")
    return failures


def collect(session, *, cluster, prefix):
    ecs, events = session.client("ecs"), session.client("events")
    manifest = {"as_of": datetime.now(UTC).isoformat(), "cluster": cluster,
                "services": [], "schedules": [], "errors": []}

    def image(task_definition):
        definition = ecs.describe_task_definition(taskDefinition=task_definition)["taskDefinition"]
        containers = definition["containerDefinitions"]
        if len(containers) != 1:
            raise ValueError(f"{task_definition}: explicit application container selection required")
        return containers[0]["image"]

    try:
        for page in ecs.get_paginator("list_services").paginate(cluster=cluster):
            for arn in page["serviceArns"]:
                result = ecs.describe_services(cluster=cluster, services=[arn])
                if result.get("failures"):
                    raise ValueError(result["failures"])
                service = result["services"][0]
                if not service["serviceName"].startswith(prefix):
                    continue
                tasks = []
                for task_page in ecs.get_paginator("list_tasks").paginate(
                    cluster=cluster, serviceName=service["serviceName"], desiredStatus="RUNNING",
                ):
                    ids = task_page["taskArns"]
                    for offset in range(0, len(ids), 100):
                        running = ecs.describe_tasks(cluster=cluster, tasks=ids[offset:offset + 100])
                        if running.get("failures"):
                            raise ValueError(running["failures"])
                        for task in running["tasks"]:
                            for container in task["containers"]:
                                tasks.append({"task_definition": task["taskDefinitionArn"],
                                              "digest": container.get("imageDigest"),
                                              "status": task["lastStatus"]})
                manifest["services"].append({"name": service["serviceName"],
                    "task_definition": service["taskDefinition"], "image": image(service["taskDefinition"]),
                    "desired": service["desiredCount"], "running": service["runningCount"],
                    "pending": service["pendingCount"], "tasks": tasks})
    except (BotoCoreError, ClientError, KeyError, ValueError) as exc:
        manifest["errors"].append(f"ECS observation failed: {exc}")
    try:
        for page in events.get_paginator("list_rules").paginate(NamePrefix=prefix):
            for rule in page["Rules"]:
                for target_page in events.get_paginator("list_targets_by_rule").paginate(Rule=rule["Name"]):
                    for target in target_page["Targets"]:
                        if "EcsParameters" not in target:
                            continue
                        definition = target["EcsParameters"]["TaskDefinitionArn"]
                        manifest["schedules"].append({"name": rule["Name"], "state": rule["State"],
                            "target": definition, "image": image(definition), "cluster": target["Arn"]})
                        if target["Arn"].rsplit("/", 1)[-1] != cluster.rsplit("/", 1)[-1]:
                            manifest["errors"].append(f"{rule['Name']}: target cluster differs from expected cluster")
    except (BotoCoreError, ClientError, KeyError, ValueError) as exc:
        manifest["errors"].append(f"EventBridge observation failed: {exc}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--region", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--service", action="append", required=True)
    parser.add_argument("--schedule", action="append", required=True)
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != args.account:
        raise SystemExit(f"Refusing wrong account {account}")
    manifest = collect(session, cluster=args.cluster, prefix=args.prefix)
    failures = validate_manifest(manifest, expected_image=args.expected_image,
        expected_digest=args.expected_digest, required_services=set(args.service),
        required_schedules=set(args.schedule))
    print(json.dumps({**manifest, "failures": failures, "verified": not failures}, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
