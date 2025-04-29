"""Observability helpers: structured JSON logging, CloudWatch Embedded Metrics and X-Ray tracing.

Import `init_observability` and call it early in your FastAPI app to activate.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from aws_embedded_metrics import metric_scope
import structlog

# X-Ray is optional – avoid hard dependency when running locally without AWS
try:
    from aws_xray_sdk.core import xray_recorder, patch_all  # type: ignore
    from aws_xray_sdk.ext.fastapi.middleware import XRayMiddleware  # type: ignore
except ImportError:  # pragma: no cover
    xray_recorder = None  # type: ignore
    patch_all = None  # type: ignore
    XRayMiddleware = None  # type: ignore

__all__ = [
    "init_observability",
    "metric_scope",  # re-export for convenience
]


def _setup_logging() -> None:
    """Configure structlog for structured logging (JSON or console)."""

    log_format = os.getenv("LOG_FORMAT", "json").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Define shared processors
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Choose renderer based on format
    if log_format == "json":
        final_processor = structlog.processors.JSONRenderer()
    else:
        final_processor = structlog.dev.ConsoleRenderer()

    # Configure structlog
    structlog.configure(
        processors=shared_processors + [final_processor],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging root logger
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    # No formatter needed here, structlog handles it via processors
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Silence noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)


def _setup_tracing(app: Optional["FastAPI"], segment_name: str = "GreatFit") -> None:  # noqa: F821
    """Attach AWS X-Ray SDK middleware if available & ENABLE_XRAY=1."""

    logger = structlog.get_logger(__name__)

    if os.getenv("ENABLE_XRAY", "1") != "1":
        return

    if xray_recorder is None or patch_all is None or XRayMiddleware is None:
        logger.warning("aws_xray_sdk not installed; skipping X-Ray setup")
        return

    # Patch common libs (sqlite3/psycopg2, requests, boto3)
    patch_all()

    if app is not None:
        try:
            app.add_middleware(XRayMiddleware, recorder=xray_recorder, segment_name=segment_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to add X-Ray middleware", exc_info=exc)


def init_observability(app: Optional["FastAPI"] = None) -> None:  # noqa: F821
    """Setup logging & tracing. Call once at process start."""

    _setup_logging()
    _setup_tracing(app)

    structlog.get_logger(__name__).info("Observability initialized")
