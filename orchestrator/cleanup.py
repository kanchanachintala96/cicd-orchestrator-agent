import os
import shutil
from .logger import get_logger

log = get_logger("cicd.cleanup")

_CLEANUP_TARGETS = [
    "__pycache__",
    ".pytest_cache",
    "*.egg-info",
    "dist",
    "build",
    ".eggs",
]


class ResourceCleaner:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def clean(self):
        log.info(f"Running cleanup in: {self.root}")
        removed = 0
        for dirpath, dirnames, _ in os.walk(self.root):
            for name in list(dirnames):
                if self._should_remove(name):
                    full = os.path.join(dirpath, name)
                    try:
                        shutil.rmtree(full)
                        log.debug(f"  Removed dir: {full}")
                        removed += 1
                        dirnames.remove(name)
                    except Exception as exc:
                        log.warning(f"  Could not remove {full}: {exc}")
        log.info(f"Cleanup complete. {removed} item(s) removed.")

    def _should_remove(self, name: str) -> bool:
        for target in _CLEANUP_TARGETS:
            if target.startswith("*"):
                if name.endswith(target[1:]):
                    return True
            else:
                if name == target:
                    return True
        return False
