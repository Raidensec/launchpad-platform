import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SERVICE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
PULL_REQUEST_PATTERN = re.compile(r"^[1-9][0-9]{0,9}$")


@dataclass(frozen=True)
class Project:
    service: str
    repository: str
    image: str


def read_project() -> Project:
    config_path = Path(__file__).resolve().parents[1] / "launchpad.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        fields = config["project"]
    except (KeyError, OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"cannot read project metadata: {error}") from error
    if not isinstance(fields, dict) or not all(
        isinstance(fields.get(key), str) for key in ("service", "repository", "image")
    ):
        raise ValueError("project metadata fields must be strings in a [project] table")
    service, repository, image = fields["service"], fields["repository"], fields["image"]
    if not SERVICE_PATTERN.fullmatch(service) or len(service) > 40:
        raise ValueError("project service name is not a valid Launchpad DNS label")
    if not valid_repository(repository) or image != image_for(repository):
        raise ValueError("project repository and image metadata are invalid")
    return Project(service, repository, image)


def valid_repository(repository: str) -> bool:
    parts = repository.split("/")
    return (
        len(parts) == 2
        and bool(OWNER_PATTERN.fullmatch(parts[0]))
        and len(parts[1]) <= 100
        and bool(REPO_PATTERN.fullmatch(parts[1]))
    )


def image_for(repository: str) -> str:
    owner, repo = repository.split("/")
    return f"ghcr.io/{owner}/{repo}".lower()


def validate_pull_request(pull_request: str) -> str:
    if not PULL_REQUEST_PATTERN.fullmatch(pull_request):
        raise ValueError("pull request number must be a positive integer with at most 10 digits")
    return pull_request


def validate_digest(digest: str) -> str:
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError("image digest must match sha256:<64 lowercase hexadecimal characters>")
    return digest


def preview_namespace(project: Project, pull_request: str) -> str:
    number = validate_pull_request(pull_request)
    fingerprint = hashlib.sha256(project.repository.lower().encode("utf-8")).hexdigest()[:8]
    return f"preview-{project.service[:28]}-{fingerprint}-pr-{number}"


def ownership_labels(project: Project, pull_request: str) -> dict[str, str]:
    return {
        "launchpad.dev/managed-by": "launchpad-platform",
        "launchpad.dev/repository-id": hashlib.sha256(
            project.repository.lower().encode("utf-8")
        ).hexdigest()[:56],
        "launchpad.dev/service": project.service,
        "launchpad.dev/ephemeral": "true",
        "launchpad.dev/pull-request": validate_pull_request(pull_request),
    }


def ownership_annotations(project: Project) -> dict[str, str]:
    return {"launchpad.dev/repository": project.repository}


def run_command(command, environment, input_text=None):
    completed = subprocess.run(
        command, env=environment, input=input_text, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise subprocess.CalledProcessError(
            completed.returncode, command, completed.stdout, completed.stderr
        )
    sys.stdout.write(completed.stdout)
    return completed.stdout


@contextmanager
def kubernetes_environment():
    encoded = os.environ.get("KUBECONFIG_B64", "")
    if not encoded:
        raise ValueError("KUBECONFIG_B64 must contain the approved cluster kubeconfig")
    try:
        kubeconfig = base64.b64decode(encoded, validate=True)
    except binascii.Error as error:
        raise ValueError("KUBECONFIG_B64 is not valid base64") from error
    if not kubeconfig:
        raise ValueError("KUBECONFIG_B64 decoded to an empty kubeconfig")
    with tempfile.TemporaryDirectory(prefix="launchpad-kube-") as temporary_directory:
        kubeconfig_path = Path(temporary_directory) / "config"
        kubeconfig_path.write_bytes(kubeconfig)
        kubeconfig_path.chmod(0o600)
        environment = os.environ.copy()
        environment["KUBECONFIG"] = str(kubeconfig_path)
        yield environment


def read_namespace(namespace, environment):
    response = run_command(
        ["kubectl", "get", "namespace", namespace, "--output", "json", "--ignore-not-found"],
        environment,
    )
    return json.loads(response) if response.strip() else None


def verify_namespace(namespace_object, project, pull_request):
    if not isinstance(namespace_object, dict):
        raise ValueError("cluster returned an invalid namespace object")
    metadata = namespace_object.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("cluster returned namespace metadata in an invalid format")
    namespace = preview_namespace(project, pull_request)
    if metadata.get("name") != namespace:
        raise ValueError("refusing to use or delete a namespace with an unexpected name")
    actual_labels = metadata.get("labels", {})
    if not isinstance(actual_labels, dict):
        raise ValueError("cluster returned namespace labels in an invalid format")
    expected_labels = ownership_labels(project, pull_request)
    if not all(actual_labels.get(key) == value for key, value in expected_labels.items()):
        raise ValueError(
            "refusing to use or delete a namespace without matching Launchpad ownership labels"
        )
    actual_annotations = metadata.get("annotations", {})
    if not isinstance(actual_annotations, dict):
        raise ValueError("cluster returned namespace annotations in an invalid format")
    if not all(
        actual_annotations.get(key) == value
        for key, value in ownership_annotations(project).items()
    ):
        raise ValueError(
            "refusing to use or delete a namespace without matching repository annotation"
        )


def ensure_namespace(project, pull_request, environment):
    namespace = preview_namespace(project, pull_request)
    existing = read_namespace(namespace, environment)
    if existing is not None:
        verify_namespace(existing, project, pull_request)
        return
    namespace_json = run_command(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "--output", "json"],
        environment,
    )
    namespace_object = json.loads(namespace_json)
    metadata = namespace_object.setdefault("metadata", {})
    metadata["labels"] = ownership_labels(project, pull_request)
    metadata["annotations"] = ownership_annotations(project)
    run_command(["kubectl", "create", "--filename", "-"], environment, json.dumps(namespace_object))


def deploy_preview(project, digest, pull_request, environment):
    checked_digest = validate_digest(digest)
    namespace = preview_namespace(project, pull_request)
    ensure_namespace(project, pull_request, environment)
    run_command(
        [
            "helm",
            "upgrade",
            "--install",
            project.service,
            "deploy/chart",
            "--namespace",
            namespace,
            "--set-string",
            f"image.repository={project.image}",
            "--set-string",
            f"image.digest={checked_digest}",
            "--atomic",
            "--wait",
            "--timeout",
            "5m",
        ],
        environment,
    )
    print(f"Preview deployed to namespace {namespace}")


def destroy_preview(project, pull_request, environment):
    namespace = preview_namespace(project, pull_request)
    existing = read_namespace(namespace, environment)
    if existing is None:
        print(f"Preview namespace {namespace} is already absent")
        return
    verify_namespace(existing, project, pull_request)
    run_command(
        ["helm", "uninstall", project.service, "--namespace", namespace, "--ignore-not-found"],
        environment,
    )
    run_command(
        ["kubectl", "delete", "namespace", namespace, "--wait=true", "--timeout=5m"], environment
    )
    print(f"Deleted owned preview namespace {namespace}")


def build_parser():
    parser = argparse.ArgumentParser(description="Manage an isolated Launchpad preview namespace")
    commands = parser.add_subparsers(dest="operation", required=True)
    deploy = commands.add_parser("deploy")
    deploy.add_argument("--pull-request", required=True)
    deploy.add_argument("--digest", required=True)
    destroy = commands.add_parser("destroy")
    destroy.add_argument("--pull-request", required=True)
    return parser


def main():
    arguments = build_parser().parse_args()
    try:
        project = read_project()
        pull_request = validate_pull_request(arguments.pull_request)
        if arguments.operation == "deploy":
            validate_digest(arguments.digest)
        with kubernetes_environment() as environment:
            if arguments.operation == "deploy":
                deploy_preview(project, arguments.digest, pull_request, environment)
            else:
                destroy_preview(project, pull_request, environment)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"preview: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            sys.stderr.write(error.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
