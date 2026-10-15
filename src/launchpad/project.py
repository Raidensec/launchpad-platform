import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from launchpad.errors import LaunchpadError
from launchpad.validation import (
    image_repository,
    validate_digest,
    validate_namespace,
    validate_repository,
    validate_service_name,
)

REQUIRED_PATHS = (
    "launchpad.toml",
    ".dockerignore",
    "requirements.txt",
    "requirements-dev.txt",
    "service/__init__.py",
    "service/app.py",
    "Dockerfile",
    "deploy/chart/Chart.yaml",
    "deploy/chart/values.yaml",
    "deploy/chart/values.schema.json",
    "deploy/chart/templates/_helpers.tpl",
    "deploy/chart/templates/deployment.yaml",
    "deploy/chart/templates/service.yaml",
    "deploy/chart/templates/service-account.yaml",
    "deploy/chart/templates/network-policy.yaml",
    "deploy/chart/templates/resource-quota.yaml",
    "deploy/chart/templates/pod-disruption-budget.yaml",
    "deploy/gitops/application.yaml",
    "scripts/preview.py",
    "scripts/promote_digest.py",
    ".github/workflows/ci.yml",
    ".github/workflows/preview.yml",
    ".github/workflows/promote.yml",
)
CHART_DIGEST = re.compile(r'^\s{2}digest:\s*(""|"sha256:[a-f0-9]{64}")\s*$')


@dataclass(frozen=True)
class Project:
    root: Path
    service: str
    repository: str
    image: str


def load_project(project_root: Path) -> Project:
    reject_symlink_path(project_root)
    config_path = project_root / "launchpad.toml"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        fields = config["project"]
        if not isinstance(fields, dict):
            raise LaunchpadError("project metadata must be a TOML table")
        if not all(
            isinstance(fields.get(name), str) for name in ("service", "repository", "image")
        ):
            raise LaunchpadError(
                "project metadata service, repository, and image fields must be strings"
            )
        service = validate_service_name(fields["service"])
        repository = validate_repository(fields["repository"])
    except (KeyError, OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise LaunchpadError(f"cannot read project metadata at {config_path}: {error}") from error
    image = image_repository(repository)
    if fields.get("image") != image:
        raise LaunchpadError("project image must match the lowercased GHCR repository")
    return Project(project_root.resolve(), service, repository, image)


def check_project(project_root: Path) -> Project:
    project = load_project(project_root)
    for relative_path in REQUIRED_PATHS:
        candidate = project.root / relative_path
        reject_symlink_path(candidate, project.root)
        if candidate.is_symlink() or not candidate.is_file():
            raise LaunchpadError(f"required project file is missing or unsafe: {relative_path}")
    values = (project.root / "deploy/chart/values.yaml").read_text(encoding="utf-8")
    digest_fields = [line for line in values.splitlines() if "digest:" in line]
    if len(digest_fields) != 1 or not CHART_DIGEST.fullmatch(digest_fields[0]):
        raise LaunchpadError(
            "chart image.digest must be empty before promotion or a valid sha256 digest"
        )
    return project


def ensure_safe_output_parent(output_parent: Path) -> Path:
    if ".." in output_parent.parts:
        raise LaunchpadError("output parent cannot contain a parent-directory segment")
    absolute_parent = output_parent.absolute()
    for ancestor in reversed(absolute_parent.parents):
        if ancestor.is_symlink():
            raise LaunchpadError(f"output path crosses a symbolic link: {ancestor}")
    if absolute_parent.is_symlink() or not absolute_parent.is_dir():
        raise LaunchpadError("output parent must be an existing, non-symbolic-link directory")
    return absolute_parent.resolve(strict=True)


def reject_symlink_path(path: Path, boundary: Path | None = None) -> None:
    absolute_path = path.absolute()
    if boundary is not None:
        absolute_boundary = boundary.absolute()
        checked_paths = [absolute_boundary]
        current = absolute_boundary
        for segment in absolute_path.relative_to(absolute_boundary).parts:
            current = current / segment
            checked_paths.append(current)
    else:
        checked_paths = list(reversed(absolute_path.parents)) + [absolute_path]
    for checked_path in checked_paths:
        if checked_path.is_symlink():
            raise LaunchpadError(f"project path crosses a symbolic link: {checked_path}")


def render_chart(project: Project, digest: str, namespace: str) -> int:
    validate_digest(digest)
    validate_namespace(namespace)
    if shutil.which("helm") is None:
        raise LaunchpadError("helm is required for render; install Helm 3.19 or newer")
    command = [
        "helm",
        "template",
        project.service,
        str(project.root / "deploy/chart"),
        "--namespace",
        namespace,
        "--set-string",
        f"image.repository={project.image}",
        "--set-string",
        f"image.digest={digest}",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        sys.stderr.write(completed.stderr)
        return completed.returncode
    sys.stdout.write(completed.stdout)
    return 0
