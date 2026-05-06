import os
from dataclasses import dataclass, field
from typing import Optional
from .logger import get_logger

log = get_logger("cicd.analyzer")


@dataclass
class ProjectConfig:
    project_type: str
    root: str
    has_requirements: bool = False
    has_setup_py: bool = False
    has_pyproject: bool = False
    has_tests: bool = False
    test_framework: str = "unittest"
    has_lint_config: bool = False
    python_executable: str = "python"
    extra: dict = field(default_factory=dict)


class ProjectAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def analyze(self) -> ProjectConfig:
        log.info(f"Analyzing project at: {self.repo_path}")

        if os.path.isfile(self.repo_path):
            raise ValueError(f"Expected a directory, got a file: {self.repo_path}")
        if not os.path.exists(self.repo_path):
            raise FileNotFoundError(f"Repo path not found: {self.repo_path}")
        if not os.access(self.repo_path, os.R_OK):
            raise PermissionError(f"No read permission on: {self.repo_path}")

        try:
            entries = os.listdir(self.repo_path)
        except PermissionError as exc:
            raise PermissionError(f"Cannot list directory: {self.repo_path}") from exc

        if not entries:
            log.warning(f"Directory is empty: {self.repo_path}")

        project_type = self._detect_type()
        config = ProjectConfig(project_type=project_type, root=self.repo_path)

        config.has_requirements = self._exists("requirements.txt")
        config.has_setup_py = self._exists("setup.py")
        config.has_pyproject = self._exists("pyproject.toml")
        config.has_tests = self._detect_tests()
        config.test_framework = self._detect_test_framework()
        config.has_lint_config = self._detect_lint()
        config.python_executable = self._detect_python()

        if project_type == "unknown":
            log.warning(
                f"Could not detect project type in '{self.repo_path}'. "
                "No Python files or known config files found."
            )

        log.info(f"Detected project type: {project_type}")
        return config

    # ------------------------------------------------------------------
    def _exists(self, filename: str) -> bool:
        return os.path.isfile(os.path.join(self.repo_path, filename))

    def _detect_type(self) -> str:
        py_markers = ["requirements.txt", "setup.py", "pyproject.toml", "*.py"]
        for marker in py_markers[:3]:
            if self._exists(marker):
                return "python"
        # walk one level for .py files
        for f in os.listdir(self.repo_path):
            if f.endswith(".py"):
                return "python"
        return "unknown"

    def _detect_tests(self) -> bool:
        for name in os.listdir(self.repo_path):
            if name.startswith("test") and name.endswith(".py"):
                return True
            if name in ("tests", "test"):
                return True
        return False

    def _detect_test_framework(self) -> str:
        #req_path = os.path.join(self.repo_path, "requirements.txt")
        #if os.path.isfile(req_path):
        #    content = open(req_path).read().lower()
        #    if "pytest" in content:
        #        return "pytest"
        return "unittest"

    def _detect_lint(self) -> bool:
        lint_files = [".flake8", ".pylintrc", "setup.cfg", "pyproject.toml"]
        return any(self._exists(f) for f in lint_files)

    def _detect_python(self) -> str:
        import shutil
        import subprocess
        for candidate in ("python3", "python", "py"):
            path = shutil.which(candidate)
            if not path:
                continue
            # On Windows, 'python' may resolve to the Store stub (exit 9009).
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return candidate
            except Exception:
                continue
        return "python"
