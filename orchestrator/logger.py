import logging
from pathlib import Path
from rich.logging import RichHandler
from rich.console import Console

console = Console(legacy_windows=False)

LOG_DIR = Path("~/.cicd_orchestrator/logs").expanduser()


def get_logger(name: str = "cicd", log_file: "str | None" = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    if log_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(fh)

    logger.propagate = False
    return logger
