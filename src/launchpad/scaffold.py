from pathlib import Path

from launchpad.errors import LaunchpadError
from launchpad.project import ensure_safe_output_parent, reject_symlink_path
from launchpad.validation import image_repository, validate_repository, validate_service_name


def template_replacements(service: str, repository: str) -> dict[str, str]:
    checked_service = validate_service_name(service)
    checked_repository = validate_repository(repository)
    return {
        "{{SERVICE_NAME}}": checked_service,
        "{{GITHUB_REPOSITORY}}": checked_repository,
        "{{IMAGE_REPOSITORY}}": image_repository(checked_repository),
    }


def render_template(template: str, replacements: dict[str, str]) -> str:
    for marker, replacement in replacements.items():
        template = template.replace(marker, replacement)
    if any(
        marker in template
        for marker in ("{{SERVICE_NAME}}", "{{GITHUB_REPOSITORY}}", "{{IMAGE_REPOSITORY}}")
    ):
        raise LaunchpadError("a scaffold template contains an unresolved project marker")
    return template


def scaffold(service: str, repository: str, output_parent: Path) -> Path:
    checked_service = validate_service_name(service)
    replacements = template_replacements(checked_service, repository)
    safe_parent = ensure_safe_output_parent(output_parent)
    destination = safe_parent / checked_service
    if destination.exists() or destination.is_symlink():
        raise LaunchpadError(f"refusing to overwrite existing path: {destination}")
    destination.mkdir()
    asset_root = Path(__file__).parent / "assets"
    for template_path in asset_root.rglob("*"):
        if (
            not template_path.is_file()
            or "__pycache__" in template_path.parts
            or template_path.suffix in {".pyc", ".pyo"}
        ):
            continue
        relative_path = Path(str(template_path.relative_to(asset_root)))
        output_path = destination / relative_path
        if ".." in relative_path.parts or relative_path.is_absolute():
            raise LaunchpadError(f"unsafe scaffold asset path: {relative_path}")
        reject_symlink_path(output_path, destination)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            template = template_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise LaunchpadError(f"scaffold asset is not UTF-8 text: {relative_path}") from error
        with output_path.open("x", encoding="utf-8", newline="\n") as output_file:
            output_file.write(render_template(template, replacements))
    return destination
