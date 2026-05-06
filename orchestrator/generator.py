from dataclasses import dataclass, field
from typing import List
from .analyzer import ProjectConfig
from .logger import get_logger

log = get_logger("cicd.generator")

# Canonical goal tokens — matched case-insensitively against the user string.
_GOAL_TESTS    = ("run tests", "test", "tests")
_GOAL_LINT     = ("lint only", "lint")
_GOAL_PIPELINE = ("run pipeline", "pipeline", "full pipeline", "all")


@dataclass
class PipelineStep:
    name: str
    command: List[str]
    cwd: str
    critical: bool = True
    max_retries: int = 1
    env: dict = field(default_factory=dict)


@dataclass
class Pipeline:
    goal: str
    steps: List[PipelineStep] = field(default_factory=list)


class PipelineGenerator:
    def __init__(self, config: ProjectConfig, goal: str):
        self.config = config
        self.goal = goal.strip().lower()

    # ── Public ────────────────────────────────────────────────────────────────
    def generate(self) -> Pipeline:
        if not self.goal.strip():
            raise ValueError("Goal must not be empty. Use: 'Run pipeline', 'Run tests', or 'Lint only'.")

        log.info(f"Generating pipeline for goal: '{self.goal}'")
        pipeline = Pipeline(goal=self.goal)

        if self.config.project_type != "python":
            log.warning(f"Unknown project type '{self.config.project_type}'; minimal pipeline.")
            pipeline.steps.append(self._echo_step("No known build steps for this project type."))
            return pipeline

        if self._matches(_GOAL_TESTS):
            pipeline.steps.extend(self._steps_tests_only())
        elif self._matches(_GOAL_LINT):
            pipeline.steps.extend(self._steps_lint_only())
        elif self._matches(_GOAL_PIPELINE):
            pipeline.steps.extend(self._steps_full_pipeline())
        else:
            log.warning(
                f"Unrecognised goal '{self.goal}' — falling back to full pipeline. "
                "Known goals: 'run pipeline' | 'run tests' | 'lint only'."
            )
            pipeline.steps.extend(self._steps_full_pipeline())

        if not pipeline.steps:
            log.warning(
                f"Goal '{self.goal}' produced no steps. "
                "Check that the project has the required files (tests, lint config, etc.)."
            )

        log.info(f"Pipeline contains {len(pipeline.steps)} step(s).")
        return pipeline

    # ── Goal matching ─────────────────────────────────────────────────────────
    def _matches(self, tokens: tuple) -> bool:
        return any(token in self.goal for token in tokens)

    # ── Step builders ─────────────────────────────────────────────────────────
    def _steps_tests_only(self) -> List[PipelineStep]:
        """goal = 'Run tests' — ONLY the test step, nothing else."""
        steps = self._test_step()
        if not steps:
            log.warning("No test step added — no test files detected in the project.")
        return steps

    def _steps_lint_only(self) -> List[PipelineStep]:
        """goal = 'Lint only' — ONLY the lint step, nothing else."""
        return [self._lint_step()]

    def _steps_full_pipeline(self) -> List[PipelineStep]:
        """goal = 'Run pipeline' — install → lint (if config) → test → run app."""
        steps: List[PipelineStep] = []
        steps.extend(self._install_step())

        if self.config.has_lint_config:
            steps.append(self._lint_step())

        steps.extend(self._test_step())
        steps.extend(self._run_app_step())
        steps.extend(self._build_step())
        return steps

    # ── Individual step factories ─────────────────────────────────────────────
    def _install_step(self) -> List[PipelineStep]:
        if not self.config.has_requirements:
            return []
        return [PipelineStep(
            name="Install dependencies",
            command=[self.config.python_executable, "-m", "pip", "install",
                     "-r", "requirements.txt", "--quiet"],
            cwd=self.config.root,
            critical=True,
            max_retries=2,
        )]

    def _lint_step(self) -> PipelineStep:
        return PipelineStep(
            name="Lint (flake8)",
            command=[self.config.python_executable, "-m", "flake8", ".",
                     "--max-line-length=120", "--statistics"],
            cwd=self.config.root,
            critical=False,
            max_retries=1,
        )

    def _test_step(self) -> List[PipelineStep]:
        if not self.config.has_tests:
            return []
        if self.config.test_framework == "pytest":
            cmd = [self.config.python_executable, "-m", "pytest", "-v", "--tb=short"]
        else:
            cmd = [self.config.python_executable, "-m", "unittest",
                   "discover", "-s", ".", "-p", "test*.py", "-v"]
        return [PipelineStep(
            name="Run tests",
            command=cmd,
            cwd=self.config.root,
            critical=True,
            max_retries=1,
        )]

    def _run_app_step(self) -> List[PipelineStep]:
        """Non-critical smoke-run of app.py if it exists."""
        import os
        app_file = os.path.join(self.config.root, "app.py")
        if not os.path.isfile(app_file):
            return []
        return [PipelineStep(
            name="Run application (smoke test)",
            command=[self.config.python_executable, "app.py"],
            cwd=self.config.root,
            critical=False,
            max_retries=1,
        )]

    def _build_step(self) -> List[PipelineStep]:
        if not (self.config.has_setup_py or self.config.has_pyproject):
            return []
        return [PipelineStep(
            name="Build package",
            command=[self.config.python_executable, "-m", "build", "--no-isolation"],
            cwd=self.config.root,
            critical=False,
            max_retries=1,
        )]

    def _echo_step(self, message: str) -> PipelineStep:
        return PipelineStep(
            name="Info",
            command=["echo", message],
            cwd=self.config.root,
            critical=False,
        )
