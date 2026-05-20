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
            if self.config.project_type in ("python", "node"):
                pipeline.steps.extend(self._steps_full_pipeline())
            elif self.config.project_type == "java":
                pipeline.steps.extend(self._generate_java_pipeline())
            pipeline.steps.extend(self._deploy_step())
        elif self.config.project_type == "node":
            pipeline.steps.extend(self._generate_node_pipeline())
        elif self.config.project_type == "java":
            pipeline.steps.extend(self._generate_java_pipeline())
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
        step = self._lint_step()
        return [step] if step else []

    def _steps_full_pipeline(self) -> List[PipelineStep]:
        steps: List[PipelineStep] = []
        steps.extend(self._install_step())
        if self.config.has_lint_config:
            lint = self._lint_step()
            if lint:
                steps.append(lint)
        steps.extend(self._framework_steps())
        steps.extend(self._test_step())
        steps.extend(self._run_app_step())
        steps.extend(self._build_step())
        return steps

    def _framework_steps(self) -> List[PipelineStep]:
        steps: List[PipelineStep] = []
        frameworks = {f.lower() for f in (self.config.frameworks or [])}
        py = self.config.python_executable

        if "django" in frameworks:
            steps.append(PipelineStep(
                name="Django system check",
                command=[py, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=30,
            ))
        if "flask" in frameworks:
            main_file = next(
                (f for f in ("app.py", "wsgi.py", "run.py") if os.path.isfile(os.path.join(self.config.root, f))),
                None,
            )
            if main_file:
                steps.append(PipelineStep(
                    name="Flask syntax check",
                    command=[py, "-m", "py_compile", main_file],
                    cwd=self.config.root,
                    critical=False,
                    max_retries=1,
                    timeout=15,
                ))
        if "fastapi" in frameworks:
            steps.append(PipelineStep(
                name="FastAPI import check",
                command=[py, "-c", "import fastapi; print('FastAPI OK')"],
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=15,
            ))
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

    def _lint_step(self):
        import shutil as _shutil
        py = self.config.python_executable

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

        if has_ruff and _shutil.which("ruff"):
            return PipelineStep(
                name="Lint (ruff)",
                command=[py, "-m", "ruff", "check", "."],
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=60,
            )
        if _shutil.which("flake8"):
            return PipelineStep(
                name="Lint (flake8)",
                command=[py, "-m", "flake8", ".", "--max-line-length=120", "--statistics"],
                cwd=self.config.root,
                critical=False,
                max_retries=1,
                timeout=60,
            )
        log.warning("No linter found on PATH (flake8/ruff) — skipping lint step.")
        return None

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
        return [
            PipelineStep(
                name="Sync with remote (git pull --rebase)",
                command=["git", "pull", "--rebase", "origin", "main"],
                cwd=self.config.root,
                critical=True,
                max_retries=1,
                timeout=60,
            ),
            PipelineStep(
                name="Deploy (git push → main)",
                command=["git", "push", "origin", "HEAD:main"],
                cwd=self.config.root,
                critical=True,
                max_retries=1,
                timeout=60,
            ),
        ]

    def _echo_step(self, message: str) -> PipelineStep:
        return PipelineStep(
            name="Info",
            command=["echo", message],
            cwd=self.config.root,
            critical=False,
        )

    # ── Java pipeline ─────────────────────────────────────────────────────────
    def _generate_java_pipeline(self) -> List[PipelineStep]:
        bt = self.config.build_tool or "maven"
        exe = getattr(self.config, "build_tool_executable", "")

        if not exe:
            binary = "mvn" if bt == "maven" else "gradle"
            install_url = (
                "https://maven.apache.org/install.html"
                if bt == "maven"
                else "https://gradle.org/install/"
            )
            return [PipelineStep(
                name=f"Prerequisite missing: {binary}",
                command=["echo",
                         f"{binary} not found on PATH. "
                         f"Install it from {install_url} and ensure it is on your PATH."],
                cwd=self.config.root,
                critical=True,
                max_retries=0,
                timeout=5,
            )]

        cmd_base = exe.split() if " " in exe else [exe]
        java_env = self._java_env(exe)
        steps: List[PipelineStep] = []

        if bt == "gradle":
            steps.append(PipelineStep(
                name="Compile (Gradle)",
                command=cmd_base + ["compileJava", "--no-daemon"],
                cwd=self.config.root, env=java_env,
                critical=True, max_retries=1, timeout=180,
            ))
            if self.config.has_tests:
                steps.append(PipelineStep(
                    name="Run tests (Gradle)",
                    command=cmd_base + ["test", "--no-daemon"],
                    cwd=self.config.root, env=java_env,
                    critical=True, max_retries=1, timeout=300,
                ))
            steps.append(PipelineStep(
                name="Package (Gradle)",
                command=cmd_base + ["build", "-x", "test", "--no-daemon"],
                cwd=self.config.root, env=java_env,
                critical=False, max_retries=1, timeout=300,
            ))
        else:
            steps.append(PipelineStep(
                name="Compile (Maven)",
                command=cmd_base + ["compile", "-q"],
                cwd=self.config.root, env=java_env,
                critical=True, max_retries=1, timeout=180,
            ))
            if self.config.has_tests:
                steps.append(PipelineStep(
                    name="Run tests (Maven/JUnit)",
                    command=cmd_base + ["test"],
                    cwd=self.config.root, env=java_env,
                    critical=True, max_retries=1, timeout=300,
                ))
            steps.append(PipelineStep(
                name="Package JAR (Maven)",
                command=cmd_base + ["package", "-DskipTests", "-q"],
                cwd=self.config.root, env=java_env,
                critical=False, max_retries=1, timeout=300,
            ))

        return steps

    def _java_env(self, exe: str) -> dict:
        import os as _os
        env = dict(_os.environ)
        if "JAVA_HOME" not in env or not _os.path.isdir(env.get("JAVA_HOME", "")):
            java_home = _os.environ.get("JAVA_HOME", "")
            for candidate in (
                r"C:\Program Files\Microsoft\jdk-21.0.11.10-hotspot",
                r"C:\Program Files\Eclipse Adoptium\jdk-21",
            ):
                if _os.path.isdir(candidate):
                    java_home = candidate
                    break
            if java_home:
                env["JAVA_HOME"] = java_home
        # Ensure the directory containing the executable is on PATH
        exe_dir = _os.path.dirname(exe)
        if exe_dir and exe_dir not in env.get("PATH", ""):
            env["PATH"] = exe_dir + _os.pathsep + env.get("PATH", "")
        java_home = env.get("JAVA_HOME", "")
        if java_home:
            java_bin = _os.path.join(java_home, "bin")
            if java_bin not in env.get("PATH", ""):
                env["PATH"] = java_bin + _os.pathsep + env["PATH"]
        return env

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
