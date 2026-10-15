import hashlib
import json

from launchpad.validation import (
    image_repository,
    validate_digest,
    validate_pull_request,
    validate_repository,
    validate_service_name,
)


def preview_namespace(service: str, repository: str, pull_request: str) -> str:
    checked_service = validate_service_name(service)
    checked_repository = validate_repository(repository)
    checked_pull_request = validate_pull_request(pull_request)
    fingerprint = hashlib.sha256(checked_repository.lower().encode("utf-8")).hexdigest()[:8]
    return f"preview-{checked_service[:28]}-{fingerprint}-pr-{checked_pull_request}"


def preview_plan(service: str, repository: str, digest: str, pull_request: str) -> str:
    checked_service = validate_service_name(service)
    checked_repository = validate_repository(repository)
    checked_digest = validate_digest(digest)
    checked_pull_request = validate_pull_request(pull_request)
    namespace = preview_namespace(checked_service, checked_repository, checked_pull_request)
    plan = {
        "mode": "plan-only",
        "repository": checked_repository,
        "release": checked_service,
        "namespace": namespace,
        "pull_request": checked_pull_request,
        "image": f"{image_repository(checked_repository)}@{checked_digest}",
        "actions": [
            "create-or-verify-owned-namespace",
            "helm-upgrade-install",
            "wait-for-readiness",
        ],
        "cluster_calls": False,
    }
    return json.dumps(plan, indent=2, sort_keys=True)


def destroy_plan(service: str, repository: str, pull_request: str) -> str:
    checked_service = validate_service_name(service)
    checked_repository = validate_repository(repository)
    checked_pull_request = validate_pull_request(pull_request)
    plan = {
        "mode": "plan-only",
        "repository": checked_repository,
        "release": checked_service,
        "namespace": preview_namespace(checked_service, checked_repository, checked_pull_request),
        "pull_request": checked_pull_request,
        "required_labels": {
            "launchpad.dev/managed-by": "launchpad-platform",
            "launchpad.dev/repository-id": hashlib.sha256(
                checked_repository.lower().encode("utf-8")
            ).hexdigest()[:56],
            "launchpad.dev/ephemeral": "true",
            "launchpad.dev/service": checked_service,
            "launchpad.dev/pull-request": checked_pull_request,
        },
        "required_annotations": {"launchpad.dev/repository": checked_repository},
        "actions": ["verify-namespace-ownership", "helm-uninstall", "delete-namespace"],
        "cluster_calls": False,
    }
    return json.dumps(plan, indent=2, sort_keys=True)
