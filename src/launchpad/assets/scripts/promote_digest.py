import argparse
import re
import sys
from pathlib import Path

DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
VALUE_PATTERN = re.compile(r'^  digest: (""|"sha256:[a-f0-9]{64}")$')


def update_digest(digest):
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError("image digest must match sha256:<64 lowercase hexadecimal characters>")
    values_path = Path(__file__).resolve().parents[1] / "deploy/chart/values.yaml"
    if values_path.is_symlink() or not values_path.is_file():
        raise ValueError("deploy/chart/values.yaml is missing or is a symbolic link")
    values = values_path.read_text(encoding="utf-8")
    digest_lines = [line for line in values.splitlines() if "digest:" in line]
    if len(digest_lines) != 1 or not VALUE_PATTERN.fullmatch(digest_lines[0]):
        raise ValueError("chart must contain exactly one supported image.digest field")
    replacement = f'  digest: "{digest}"'
    if digest_lines[0] == replacement:
        return False
    values_path.write_text(
        values.replace(digest_lines[0], replacement, 1), encoding="utf-8", newline="\n"
    )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Set the chart image to a published immutable digest"
    )
    parser.add_argument("digest")
    arguments = parser.parse_args()
    try:
        changed = update_digest(arguments.digest)
    except (OSError, ValueError) as error:
        print(f"promote-digest: {error}", file=sys.stderr)
        return 2
    print("Image digest updated" if changed else "Image digest already matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
