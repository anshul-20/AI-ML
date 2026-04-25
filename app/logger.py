"""
Feature 5: Observability & Logging System
Structured logging with request ID correlation, timing, and event tracking.
"""

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional

# Context variable to hold per-request correlation ID
_request_id: ContextVar[str] = ContextVar("request_id", default="none")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(rid: Optional[str] = None) -> str:
    rid = rid or str(uuid.uuid4())[:8]
    _request_id.set(rid)
    return rid


class CorrelationFilter(logging.Filter):
    """Inject request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging() -> None:
    """Configure structured logging with correlation ID support."""
    fmt = "%(asctime)s | %(levelname)-8s | [%(request_id)s] | %(name)s | %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationFilter())

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[handler],
        force=True,
    )


def log_event(logger: logging.Logger, event: str, **kwargs: Any) -> None:
    """Log a structured event with key=value pairs."""
    parts = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("event=%s | %s", event, parts)


def timed(logger: logging.Logger, label: str):
    """Decorator that logs execution time of an async function."""
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                log_event(logger, label, status="ok", latency_ms=elapsed_ms)
                return result
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                log_event(logger, label, status="error", latency_ms=elapsed_ms, error=str(exc)[:120])
                raise
        return wrapper
    return decorator
