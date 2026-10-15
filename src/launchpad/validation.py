import re

from launchpad.errors import LaunchpadError

SERVICE_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
OWNER_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_NAME = re.compile(r"^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$")
NAMESPACE_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
IMAGE_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
PULL_REQUEST = re.compile(r"^[1-9][0-9]{0,9}$")


def validate_service_name(service_name: str) -> str:
    if len(service_name) > 40 or not SERVICE_NAME.fullmatch(service_name):
        raise LaunchpadError(
            "service name must be a DNS label of 1-40 lowercase letters, digits, or hyphens"
        )
    return service_name


def validate_repository(repository: str) -> str:
    parts = repository.split("/")
    if (
        len(parts) != 2
        or not OWNER_NAME.fullmatch(parts[0])
        or len(parts[1]) > 100
        or not REPO_NAME.fullmatch(parts[1])
    ):
        raise LaunchpadError("repository must be a valid GitHub owner/repository pair")
    return f"{parts[0]}/{parts[1]}"


def image_repository(repository: str) -> str:
    owner, repo = validate_repository(repository).split("/")
    return f"ghcr.io/{owner}/{repo}".lower()


def validate_digest(digest: str) -> str:
    if not IMAGE_DIGEST.fullmatch(digest):
        raise LaunchpadError("image digest must match sha256:<64 lowercase hexadecimal characters>")
    return digest


def validate_namespace(namespace: str) -> str:
    if len(namespace) > 63 or not NAMESPACE_NAME.fullmatch(namespace):
        raise LaunchpadError(
            "namespace must be a DNS label of 1-63 lowercase letters, digits, or hyphens"
        )
    return namespace


def validate_pull_request(pull_request: str) -> str:
    if not PULL_REQUEST.fullmatch(pull_request):
        raise LaunchpadError(
            "pull request number must be a positive integer with at most 10 digits"
        )
    return pull_request
