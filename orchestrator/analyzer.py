import json
import os
import shutil
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
    node_package_manager: str = ""
    build_tool: str = ""
    build_tool_executable: str = ""
    frameworks: list = field(default_factory=list)
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

        if project_type == "node":
            config.node_package_manager = self._detect_node_pm()
            config.has_tests = self._detect_node_tests()
            config.test_framework = self._detect_node_test_framework()
            config.has_lint_config = self._detect_node_lint()
            config.frameworks = self._detect_node_frameworks()
        elif project_type == "java":
            config.build_tool = self._detect_build_tool()
            config.build_tool_executable = self._detect_java_executable(config.build_tool)
            config.has_tests = self._detect_java_tests()
            config.test_framework = "junit"
            config.frameworks = self._detect_java_frameworks()
        else:
            config.has_requirements = self._exists("requirements.txt")
            config.has_setup_py = self._exists("setup.py")
            config.has_pyproject = self._exists("pyproject.toml")
            config.has_tests = self._detect_tests()
            config.test_framework = self._detect_test_framework()
            config.has_lint_config = self._detect_lint()
            config.python_executable = self._detect_python()
            config.frameworks = self._detect_python_frameworks()

        if project_type == "unknown":
            log.warning(
                f"Could not detect project type in '{self.repo_path}'. "
                "No Python files or known config files found."
            )

        log.info(f"Detected project type: {project_type}")
        return config

    # ── Shared helpers ────────────────────────────────────────────────────────
    def _exists(self, filename: str) -> bool:
        return os.path.isfile(os.path.join(self.repo_path, filename))

    def _detect_type(self) -> str:
        if self._exists("package.json"):
            return "node"
        if self._exists("pom.xml") or self._exists("build.gradle") or self._exists("build.gradle.kts"):
            return "java"
        py_markers = ["requirements.txt", "setup.py", "pyproject.toml"]
        for marker in py_markers:
            if self._exists(marker):
                return "python"
        for f in os.listdir(self.repo_path):
            if f.endswith(".py"):
                return "python"
        # detect java by scanning for .java files in src/
        src_dir = os.path.join(self.repo_path, "src")
        if os.path.isdir(src_dir):
            for root, _, files in os.walk(src_dir):
                if any(f.endswith(".java") for f in files):
                    return "java"
        return "unknown"

    # ── Python detection ──────────────────────────────────────────────────────
    def _detect_tests(self) -> bool:
        for name in os.listdir(self.repo_path):
            if name.startswith("test") and name.endswith(".py"):
                return True
            if name in ("tests", "test"):
                return True
        return False

    def _detect_test_framework(self) -> str:
        if self._exists("pytest.ini") or self._exists("conftest.py"):
            return "pytest"
        req_path = os.path.join(self.repo_path, "requirements.txt")
        if os.path.isfile(req_path):
            try:
                content = open(req_path, encoding="utf-8", errors="ignore").read().lower()
                if "pytest" in content:
                    return "pytest"
            except Exception:
                pass
        pyproject_path = os.path.join(self.repo_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                content = open(pyproject_path, encoding="utf-8", errors="ignore").read().lower()
                if "pytest" in content:
                    return "pytest"
            except Exception:
                pass
        return "unittest"

    def _detect_lint(self) -> bool:
        lint_files = [".flake8", ".pylintrc", "setup.cfg", "pyproject.toml", "ruff.toml", ".ruff.toml"]
        return any(self._exists(f) for f in lint_files)

    def _detect_python(self) -> str:
        import shutil
        import subprocess
        for candidate in ("python3", "python", "py"):
            path = shutil.which(candidate)
            if not path:
                continue
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return candidate
            except Exception:
                continue
        return "python"

    # ── Node.js detection ─────────────────────────────────────────────────────
    def _detect_node_pm(self) -> str:
        if self._exists("pnpm-lock.yaml"):
            return "pnpm"
        if self._exists("yarn.lock"):
            return "yarn"
        return "npm"

    def _detect_node_tests(self) -> bool:
        pkg = self._read_package_json()
        if not pkg:
            return False
        if "test" in pkg.get("scripts", {}):
            return True
        dev_deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
        return any(k in dev_deps for k in ("jest", "mocha", "vitest", "jasmine", "@jest/core"))

    def _detect_node_test_framework(self) -> str:
        pkg = self._read_package_json()
        if not pkg:
            return "jest"
        dev_deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
        for fw in ("vitest", "mocha", "jasmine", "jest"):
            if fw in dev_deps:
                return fw
        return "jest"

    def _detect_node_lint(self) -> bool:
        lint_files = [
            ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml",
            ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs",
        ]
        if any(self._exists(f) for f in lint_files):
            return True
        pkg = self._read_package_json()
        if pkg:
            dev_deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
            return "eslint" in dev_deps
        return False

    def _read_package_json(self) -> dict:
        path = os.path.join(self.repo_path, "package.json")
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _detect_node_frameworks(self) -> list:
        pkg = self._read_package_json()
        if not pkg:
            return []
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        found = []
        fw_map = {
            "react": "React", "vue": "Vue", "next": "Next.js",
            "nuxt": "Nuxt", "express": "Express", "fastify": "Fastify",
            "svelte": "@sveltejs/kit", "angular": "@angular/core",
        }
        for key, label in fw_map.items():
            if key in all_deps or label in all_deps:
                found.append(label if label in all_deps else key.capitalize())
        return found

    # ── Java detection ────────────────────────────────────────────────────────
    def _detect_build_tool(self) -> str:
        if self._exists("pom.xml"):
            return "maven"
        if self._exists("build.gradle") or self._exists("build.gradle.kts"):
            return "gradle"
        return "maven"

    def _detect_java_executable(self, build_tool: str) -> str:
        wrapper = "mvnw" if build_tool == "maven" else "gradlew"
        if os.path.isfile(os.path.join(self.repo_path, wrapper)):
            return f"./{wrapper}"
        binary = "mvn" if build_tool == "maven" else "gradle"
        found = shutil.which(binary)
        if found:
            return found
        # Fallback: scan common install locations when PATH isn't updated yet
        home = os.path.expanduser("~")
        candidates = (
            [os.path.join(home, "maven"), os.path.join(home, ".maven")]
            if build_tool == "maven"
            else [os.path.join(home, "gradle"), os.path.join(home, ".gradle")]
        )
        ext = ".cmd" if os.name == "nt" else ""
        for base in candidates:
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base), reverse=True):
                candidate = os.path.join(base, entry, "bin", f"{binary}{ext}")
                if os.path.isfile(candidate):
                    return candidate
        return ""

    def _detect_java_tests(self) -> bool:
        test_dir = os.path.join(self.repo_path, "src", "test")
        if not os.path.isdir(test_dir):
            return False
        for root, _, files in os.walk(test_dir):
            if any(f.endswith(".java") for f in files):
                return True
        return False

    def _detect_java_frameworks(self) -> list:
        found = []
        pom_path = os.path.join(self.repo_path, "pom.xml")
        gradle_path = os.path.join(self.repo_path, "build.gradle")
        content = ""
        for path in (pom_path, gradle_path):
            if os.path.isfile(path):
                try:
                    content += open(path, encoding="utf-8", errors="ignore").read().lower()
                except Exception:
                    pass
        fw_map = {
            "spring-boot": "Spring Boot",
            "spring-web": "Spring Web",
            "quarkus": "Quarkus",
            "micronaut": "Micronaut",
            "junit-jupiter": "JUnit 5",
            "junit": "JUnit",
            "mockito": "Mockito",
            "hibernate": "Hibernate",
            "jakarta": "Jakarta EE",
        }
        for key, label in fw_map.items():
            if key in content:
                found.append(label)
        return found

    # ── Python framework detection ─────────────────────────────────────────────
    def _detect_python_frameworks(self) -> list:
        found = []
        sources = []
        for fname in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            path = os.path.join(self.repo_path, fname)
            if os.path.isfile(path):
                try:
                    sources.append(open(path, encoding="utf-8", errors="ignore").read().lower())
                except Exception:
                    pass
        content = "\n".join(sources)
        fw_map = {
            "django": "Django",
            "flask": "Flask",
            "fastapi": "FastAPI",
            "streamlit": "Streamlit",
            "tornado": "Tornado",
            "aiohttp": "aiohttp",
            "starlette": "Starlette",
            "celery": "Celery",
            "sqlalchemy": "SQLAlchemy",
            "pydantic": "Pydantic",
        }
        for key, label in fw_map.items():
            if key in content:
                found.append(label)
        return found
