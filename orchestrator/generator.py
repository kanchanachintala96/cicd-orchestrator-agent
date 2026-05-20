import json
import os
from dataclasses import dataclass, field
from typing import List
from .analyzer import ProjectConfig
from .logger import get_logger

log = get_logger("cicd.generator")

_GOAL_TESTS    = ("run tests", "test", "tests")
_GOAL_LINT     = ("lint only", "lint")
_GOAL_PIPELINE = ("run pipeline", "pipeline", "full pipeline", "all")
_GOAL_DEPLOY   = ("deploy", "release", "deploy to production")


@dataclass
class PipelineStep:
    name: str
    command: List[str]
    cwd: str
    critical: bool = True
    max_retries: int = 1
    env: dict = field(default_factory=dict)
    timeout: int = 300


@dataclass
class Pipeline:
    goal: str
    steps: List[PipelineStep] = field(default_factory=list)


class PipelineGenerator:
    def __init__(self, config: ProjectConfig, goal: str):
        self.config = config
        self.goal = goal.strip().lower()

    def generate(self) -> Pipeline:
        if not self.goal.strip():
            raise ValueError("Goal must not be empty. Use: 'Run pipeline', 'Run tests', or 'Lint only'.")

        log.info(f"Generating pipeline for goal: '{self.goal}'")
        pipeline = Pipeline(goal=self.goal)

        if self._matches(_GOAL_DEPLOY):
            pipeline.steps.extend(self._steps_full_pipeline() if self.config.project_type in ("python", "node") else [])
            pipeline.steps.extend(self._deploy_step())
        elif self.config.project_type == "node":
            pipeline.steps.extend(self._generate_node_pipeline())
        elif self.config.project_type == "python":
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
        else:
            log.warning(f"Unknown project type '{self.config.project_type}'; minimal pipeline.")
            pipeline.steps.append(self._echo_step("No known build steps for this project type."))

        if not pipeline.steps:
            log.warning(
                f"Goal '{self.goal}' produced no steps. "
                "Check that the project has the required files (tests, lint config, etc.)."
            )

        log.info(f"Pipeline contains {len(pipeline.steps)} step(s).")
        return pipeline

    def _matches(self, tokens: tuple) -> bool:
        return any(token in self.goal for token in tokens)

    # ── Python pipeline ───────────────────────────────────────────────────────
    def _steps_tests_only(self) -> List[PipelineStep]:
        steps = self._test_step()
        if not steps:
            log.warning("No test step added — no test files detected in the project.")
        return steps

    def _steps_lint_only(self) -> List[PipelineStep]:
        return [self._lint_step()]

    def _steps_full_pipeline(self) -> List[PipelineStep]:
        steps: List[PipelineStep] = []
        steps.extend(self._install_step())
        if self.config.has_lint_config:
            steps.append(self._lint_step())
        steps.extend(self._test_step())
        steps.extend(self._run_app_step())
        steps.extend(self._build_step())
        return steps

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
            timeout=120,
        )]

    def _lint_step(self) -> PipelineStep:
        has_ruff = (
            os.path.isfile(os.path.join(self.config.root, "ruff.toml")) or
            os.path.isfile(os.path.join(self.config.root, ".ruff.toml"))
        )
        if not has_ruff and self.config.has_pyproject:
            try:
                with open(os.path.join(self.config.root, "pyproject.toml"), encoding="utf-8") as f:
                    has_ruff = "[tool.ruff]" in f.read()
            except Exception:
                pass

        if has_ruff:
            return PipelineStep(
                name="Lint (ruff)",
                command=[self.config.python_executable, "-m", "ruff", "check", "."],
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=60,
            )
        return PipelineStep(
            name="Lint (flake8)",
            command=[self.config.python_executable, "-m", "flake8", ".",
                     "--max-line-length=120", "--statistics"],
            cwd=self.config.root,
            critical=False,
            max_retries=1,
            timeout=60,
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
            timeout=180,
        )]

    def _run_app_step(self) -> List[PipelineStep]:
        app_file = os.path.join(self.config.root, "app.py")
        if not os.path.isfile(app_file):
            return []
        return [PipelineStep(
            name="Run application (smoke test)",
            command=[self.config.python_executable, "app.py"],
            cwd=self.config.root,
            critical=False,
            max_retries=1,
            timeout=30,
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
            timeout=120,
        )]

    def _deploy_step(self) -> list:
        return [PipelineStep(
            name="Deploy (git push → main)",
            command=["git", "push", "origin", "HEAD:main"],
            cwd=self.config.root,
            critical=True,
            max_retries=1,
            timeout=60,
        )]

    def _echo_step(self, message: str) -> PipelineStep:
        return PipelineStep(
            name="Info",
            command=["echo", message],
            cwd=self.config.root,
            critical=False,
        )

    # ── Node.js pipeline ──────────────────────────────────────────────────────
    def _generate_node_pipeline(self) -> List[PipelineStep]:
        pm = self.config.node_package_manager or "npm"
        steps: List[PipelineStep] = []

        install_cmd = {
            "yarn": ["yarn", "install", "--frozen-lockfile"],
            "pnpm": ["pnpm", "install", "--frozen-lockfile"],
            "npm":  ["npm", "ci"],
        }.get(pm, ["npm", "ci"])
        steps.append(PipelineStep(
            name=f"Install dependencies ({pm})",
            command=install_cmd,
            cwd=self.config.root,
            critical=True,
            max_retries=2,
            timeout=180,
        ))

        if self.config.has_lint_config:
            lint_cmd = {
                "yarn": ["yarn", "lint"],
                "pnpm": ["pnpm", "run", "lint"],
                "npm":  ["npm", "run", "lint"],
            }.get(pm, ["npm", "run", "lint"])
            steps.append(PipelineStep(
                name="Lint (ESLint)",
                command=lint_cmd,
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=60,
            ))

        if self.config.has_tests:
            test_cmd = {
                "yarn": ["yarn", "test", "--passWithNoTests"],
                "pnpm": ["pnpm", "run", "test"],
                "npm":  ["npm", "test"],
            }.get(pm, ["npm", "test"])
            steps.append(PipelineStep(
                name=f"Run tests ({self.config.test_framework})",
                command=test_cmd,
                cwd=self.config.root,
                critical=True,
                max_retries=1,
                timeout=180,
            ))

        pkg_path = os.path.join(self.config.root, "package.json")
        try:
            with open(pkg_path, encoding="utf-8") as f:
                pkg = json.load(f)
            if "build" in pkg.get("scripts", {}):
                build_cmd = {
                    "yarn": ["yarn", "build"],
                    "pnpm": ["pnpm", "run", "build"],
                    "npm":  ["npm", "run", "build"],
                }.get(pm, ["npm", "run", "build"])
                steps.append(PipelineStep(
                    name="Build",
                    command=build_cmd,
                    cwd=self.config.root,
                    critical=False,
                    max_retries=1,
                    timeout=300,
                ))
        except Exception:
            pass

        return steps
