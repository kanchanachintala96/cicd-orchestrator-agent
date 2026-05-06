import subprocess
import os
from typing import List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich import box

from .generator import Pipeline, PipelineStep
from .retry import with_retry
from .logger import get_logger

log = get_logger("cicd.executor")
console = Console(legacy_windows=False)


class StepFailedError(RuntimeError):
    pass


class PipelineExecutor:
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.results: List[dict] = []

    def run(self) -> bool:
        console.print(Panel(
            f"[bold cyan]Goal:[/] {self.pipeline.goal}\n"
            f"[bold cyan]Steps:[/] {len(self.pipeline.steps)}",
            title="[bold white]CI/CD Pipeline[/]",
            border_style="bright_blue",
        ))

        all_passed = True
        total = len(self.pipeline.steps)

        for idx, step in enumerate(self.pipeline.steps, start=1):
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[bold blue][{idx}/{total}][/] [white]{step.name}[/]"),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("running", total=None)
                success = self._run_step(step)

            if success:
                console.print(f"  [bold green][+][/]  [bold]{step.name}[/]  [bold green]PASS[/]")
            else:
                console.print(f"  [bold red][-][/]  [bold]{step.name}[/]  [bold red]FAIL[/]")

            self.results.append({"step": step.name, "status": "PASS" if success else "FAIL"})

            if not success and step.critical:
                log.error(f"Critical step '[bold]{step.name}[/]' failed — aborting pipeline.")
                all_passed = False
                break
            if not success:
                log.warning(f"Non-critical step '[bold]{step.name}[/]' failed — continuing.")
                all_passed = False

        self._print_summary()
        return all_passed

    # ------------------------------------------------------------------
    def _run_step(self, step: PipelineStep) -> bool:
        if not step.command:
            log.warning(f"Step '[bold]{step.name}[/]' has an empty command — skipping.")
            return False

        if not os.path.isdir(step.cwd):
            log.error(f"Working directory does not exist for step '[bold]{step.name}[/]': {step.cwd}")
            return False

        def attempt():
            env = {**os.environ, **step.env}
            try:
                result = subprocess.run(
                    step.command,
                    cwd=step.cwd,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                raise StepFailedError("Step timed out after 300 seconds.")
            except FileNotFoundError:
                raise StepFailedError(
                    f"Command not found: '{step.command[0]}'. "
                    "Is it installed and on PATH?"
                )

            if result.stdout:
                for line in result.stdout.splitlines():
                    log.debug(f"  stdout | {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    log.debug(f"  stderr | {line}")
            if result.returncode != 0:
                raise StepFailedError(f"Exit code {result.returncode}")

        try:
            with_retry(attempt, max_attempts=step.max_retries, delay=1.0,
                       exceptions=(StepFailedError,))
            return True
        except StepFailedError as exc:
            log.error(f"Step '[bold]{step.name}[/]' failed after {step.max_retries} attempt(s): {exc}")
            return False
        except Exception as exc:
            log.error(f"Unexpected error in '[bold]{step.name}[/]': {exc}")
            return False

    def _print_summary(self):
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = len(self.results) - passed

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        table.add_column("Step", style="white", min_width=35)
        table.add_column("Result", justify="center", min_width=8)

        for r in self.results:
            result_cell = "[bold green]PASS[/]" if r["status"] == "PASS" else "[bold red]FAIL[/]"
            table.add_row(r["step"], result_cell)

        overall = "[bold green]ALL PASSED[/]" if failed == 0 else f"[bold red]{failed} FAILED[/]"
        console.print()
        console.print(Panel(
            table,
            title="[bold white]Pipeline Summary[/]",
            subtitle=f"{passed}/{len(self.results)} steps passed  |  {overall}",
            border_style="green" if failed == 0 else "red",
        ))
