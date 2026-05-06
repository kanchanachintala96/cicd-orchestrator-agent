"""CI/CD Orchestrator Agent — entry point.

Usage:
    python main.py --repo ./sample_app --goal "Run pipeline"
    python main.py --repo ./sample_app --goal "Run tests" --no-cleanup
"""

import argparse
import sys

# Force UTF-8 output on Windows so Rich box/rule characters render correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from rich.rule import Rule

from orchestrator.analyzer import ProjectAnalyzer
from orchestrator.generator import PipelineGenerator
from orchestrator.executor import PipelineExecutor
from orchestrator.cleanup import ResourceCleaner
from orchestrator.logger import get_logger, console

log = get_logger("cicd.main")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="CI/CD Orchestrator Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the repository / project to build.",
    )
    parser.add_argument(
        "--goal",
        required=True,
        help='Goal description, e.g. "Run pipeline", "Run tests", "Lint only".',
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Skip post-run resource cleanup.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if not args.goal.strip():
        log.error("--goal cannot be empty. Use: 'Run pipeline', 'Run tests', or 'Lint only'.")
        return 1

    console.print(Rule("[bold magenta]CI/CD Orchestrator Agent[/]", style="magenta"))
    log.info(f"Repository : [cyan]{args.repo}[/]")
    log.info(f"Goal       : [cyan]{args.goal}[/]")

    # 1. Analyze
    try:
        analyzer = ProjectAnalyzer(args.repo)
        config = analyzer.analyze()
    except FileNotFoundError as exc:
        log.error(f"Repository not found: {exc}")
        return 1
    except ValueError as exc:
        log.error(f"Invalid repository path: {exc}")
        return 1
    except PermissionError as exc:
        log.error(f"Permission denied: {exc}")
        return 1

    # 2. Generate pipeline
    try:
        generator = PipelineGenerator(config, goal=args.goal)
        pipeline = generator.generate()
    except ValueError as exc:
        log.error(f"Invalid goal: {exc}")
        return 1

    if not pipeline.steps:
        log.warning("No pipeline steps generated. Nothing to do.")
        return 0

    # 3. Execute
    try:
        executor = PipelineExecutor(pipeline)
        success = executor.run()
    except KeyboardInterrupt:
        log.warning("Pipeline interrupted by user.")
        return 1

    # 4. Cleanup
    if not args.no_cleanup:
        console.print(Rule("[dim]Cleanup[/]", style="dim"))
        try:
            ResourceCleaner(args.repo).clean()
        except Exception as exc:
            log.warning(f"Cleanup failed (non-critical): {exc}")

    console.print(Rule(style="magenta"))
    return 0 if success else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(1)
