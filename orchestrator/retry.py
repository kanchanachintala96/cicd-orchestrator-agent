import time
import functools
from typing import Callable, Type, Tuple
from .logger import get_logger

log = get_logger("cicd.retry")


def with_retry(
    fn: Callable,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Call *fn* up to *max_attempts* times, with exponential backoff."""
    attempt = 0
    wait = delay
    while True:
        attempt += 1
        try:
            return fn()
        except exceptions as exc:
            if attempt >= max_attempts:
                log.error(f"All {max_attempts} attempts failed. Last error: {exc}")
                raise
            log.warning(f"Attempt {attempt}/{max_attempts} failed: {exc}. Retrying in {wait:.1f}s…")
            time.sleep(wait)
            wait *= backoff


def retryable(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator version of with_retry."""
    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return with_retry(
                lambda: fn(*args, **kwargs),
                max_attempts=max_attempts,
                delay=delay,
                backoff=backoff,
            )
        return wrapper
    return decorator
