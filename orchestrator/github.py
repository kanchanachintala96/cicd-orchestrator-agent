import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from .logger import get_logger

log = get_logger("cicd.github")

_API = "https://api.github.com"


@dataclass
class RepoInfo:
    owner: str
    name: str
    full_name: str
    description: str
    default_branch: str
    language: str
    stars: int
    forks: int
    private: bool
    clone_url: str
    html_url: str


@dataclass
class CloneResult:
    success: bool
    local_path: str
    branch: str
    commit_sha: str = ""
    error: str = ""


class GitHubConnector:
    def __init__(self, token: Optional[str] = None):
        self.token = token.strip() if token else None
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"

    # ── Auth ──────────────────────────────────────────────────────────────────
    def whoami(self) -> Optional[str]:
        """Return the authenticated username, or None for unauthenticated."""
        try:
            r = self._session.get(f"{_API}/user", timeout=8)
            if r.status_code == 200:
                return r.json().get("login")
        except Exception:
            pass
        return None

    # ── Repo info ─────────────────────────────────────────────────────────────
    def get_repo(self, owner: str, repo: str) -> RepoInfo:
        r = self._get(f"/repos/{owner}/{repo}")
        return RepoInfo(
            owner          = r["owner"]["login"],
            name           = r["name"],
            full_name      = r["full_name"],
            description    = r.get("description") or "",
            default_branch = r.get("default_branch", "main"),
            language       = r.get("language") or "Unknown",
            stars          = r.get("stargazers_count", 0),
            forks          = r.get("forks_count", 0),
            private        = r.get("private", False),
            clone_url      = r["clone_url"],
            html_url       = r["html_url"],
        )

    def list_branches(self, owner: str, repo: str) -> List[str]:
        branches = self._get(f"/repos/{owner}/{repo}/branches?per_page=50")
        return [b["name"] for b in branches]

    # ── Clone ─────────────────────────────────────────────────────────────────
    def clone(self, info: RepoInfo, target_dir: str, branch: str) -> CloneResult:
        if not shutil.which("git"):
            return CloneResult(
                success=False, local_path=target_dir, branch=branch,
                error="git is not installed or not on PATH.",
            )

        clone_url = info.clone_url
        if self.token:
            clone_url = clone_url.replace("https://", f"https://{self.token}@")

        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)

        log.info(f"Cloning {info.full_name}@{branch} → {target_dir}")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", branch, clone_url, target_dir],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return CloneResult(
                    success=False, local_path=target_dir, branch=branch,
                    error=result.stderr.strip(),
                )
        except subprocess.TimeoutExpired:
            return CloneResult(
                success=False, local_path=target_dir, branch=branch,
                error="Clone timed out after 120 seconds.",
            )

        sha = self._head_sha(target_dir)
        log.info(f"Clone complete. HEAD={sha[:7] if sha else '?'}")
        return CloneResult(success=True, local_path=target_dir, branch=branch, commit_sha=sha)

    # ── Commit status ─────────────────────────────────────────────────────────
    def post_commit_status(
        self, owner: str, repo: str, sha: str,
        state: str, description: str, context: str = "ci/orchestrator",
    ) -> bool:
        """Post a GitHub commit status (requires token with repo scope)."""
        if not self.token or not sha:
            return False
        try:
            r = self._session.post(
                f"{_API}/repos/{owner}/{repo}/statuses/{sha}",
                json={"state": state, "description": description[:140], "context": context},
                timeout=8,
            )
            return r.status_code == 201
        except Exception as exc:
            log.warning(f"Could not post commit status: {exc}")
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get(self, path: str):
        url = f"{_API}{path}"
        try:
            r = self._session.get(url, timeout=10)
        except requests.ConnectionError:
            raise RuntimeError("No internet connection or GitHub is unreachable.")
        except requests.Timeout:
            raise RuntimeError(f"Request timed out: {url}")
        if r.status_code == 401:
            raise PermissionError("GitHub token is invalid or expired.")
        if r.status_code == 403:
            raise PermissionError("GitHub rate limit hit or insufficient token scope.")
        if r.status_code == 404:
            raise FileNotFoundError(f"Not found on GitHub: {path}")
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _head_sha(repo_dir: str) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_dir, capture_output=True, text=True,
            )
            return r.stdout.strip()
        except Exception:
            return ""


def parse_repo_input(text: str):
    """Parse 'owner/repo' or a full GitHub URL into (owner, repo)."""
    text = text.strip().rstrip("/")
    patterns = [
        r"github\.com[:/]([^/]+)/([^/\s\.]+?)(?:\.git)?$",
        r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1), m.group(2)
    raise ValueError(
        f"Cannot parse '{text}'. Use 'owner/repo' or a GitHub URL."
    )
