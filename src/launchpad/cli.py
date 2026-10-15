import argparse
import sys
from pathlib import Path

from launchpad.errors import LaunchpadError
from launchpad.plans import destroy_plan, preview_plan
from launchpad.project import check_project, render_chart
from launchpad.scaffold import scaffold


def add_init_command(commands: argparse._SubParsersAction) -> None:
    command = commands.add_parser("init", help="scaffold an independent Python service project")
    command.add_argument("service")
    command.add_argument("--repository", required=True, help="GitHub owner/repository")
    command.add_argument("--output-parent", type=Path, default=Path.cwd())
    command.set_defaults(run=run_init)


def add_check_command(commands: argparse._SubParsersAction) -> None:
    command = commands.add_parser("check", help="validate project metadata and required files")
    command.add_argument("project", type=Path)
    command.set_defaults(run=run_check)


def add_render_command(commands: argparse._SubParsersAction) -> None:
    command = commands.add_parser("render", help="render the Helm chart with an immutable image")
    command.add_argument("project", type=Path)
    command.add_argument("--digest", required=True)
    command.add_argument("--namespace")
    command.set_defaults(run=run_render)


def add_plan_commands(commands: argparse._SubParsersAction) -> None:
    preview = commands.add_parser("preview-plan", help="print a non-mutating preview plan")
    preview.add_argument("service")
    preview.add_argument("--repository", required=True)
    preview.add_argument("--digest", required=True)
    preview.add_argument("--pull-request", required=True)
    preview.set_defaults(run=run_preview_plan)
    destroy = commands.add_parser("destroy-plan", help="print a non-mutating teardown plan")
    destroy.add_argument("service")
    destroy.add_argument("--repository", required=True)
    destroy.add_argument("--pull-request", required=True)
    destroy.set_defaults(run=run_destroy_plan)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="launchpad")
    commands = parser.add_subparsers(dest="command", required=True)
    add_init_command(commands)
    add_check_command(commands)
    add_render_command(commands)
    add_plan_commands(commands)
    return parser


def run_init(arguments: argparse.Namespace) -> int:
    destination = scaffold(arguments.service, arguments.repository, arguments.output_parent)
    print(f"Created service project at {destination}")
    return 0


def run_check(arguments: argparse.Namespace) -> int:
    project = check_project(arguments.project)
    print(f"Valid service project: {project.service} ({project.repository})")
    return 0


def run_render(arguments: argparse.Namespace) -> int:
    project = check_project(arguments.project)
    namespace = arguments.namespace or project.service
    return render_chart(project, arguments.digest, namespace)


def run_preview_plan(arguments: argparse.Namespace) -> int:
    print(
        preview_plan(
            arguments.service, arguments.repository, arguments.digest, arguments.pull_request
        )
    )
    return 0


def run_destroy_plan(arguments: argparse.Namespace) -> int:
    print(destroy_plan(arguments.service, arguments.repository, arguments.pull_request))
    return 0


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        return arguments.run(arguments)
    except (LaunchpadError, OSError) as error:
        print(f"launchpad: {error}", file=sys.stderr)
        return 2
