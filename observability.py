"""Observability helpers: structured JSON logging, CloudWatch Embedded Metrics and X-Ray tracing.

Import `init_observability` and call it early in your FastAPI app to activate.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from json_log_formatter import JSONFormatter
from aws_embedded_metrics import metric_scope

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
    """Configure root logger to emit JSON if LOG_FORMAT=json (default)."""

    log_format = os.getenv("LOG_FORMAT", "json").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    root = logging.getLogger()

    if log_format == "json":
        formatter = JSONFormatter()
    else:  # plain text
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Replace existing handlers to avoid duplicate logs
    root.handlers = [handler]
    root.setLevel(log_level)


def _setup_tracing(app: Optional["FastAPI"], segment_name: str = "GreatFit") -> None:  # noqa: F821
    """Attach AWS X-Ray SDK middleware if available & ENABLE_XRAY=1."""

    if os.getenv("ENABLE_XRAY", "1") != "1":
        return

    if xray_recorder is None or patch_all is None or XRayMiddleware is None:
        logging.getLogger(__name__).warning("aws_xray_sdk not installed; skipping X-Ray setup")
        return

    # Patch common libs (sqlite3/psycopg2, requests, boto3)
    patch_all()

    if app is not None:
        try:
            app.add_middleware(XRayMiddleware, recorder=xray_recorder, segment_name=segment_name)
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning("Failed to add X-Ray middleware: %s", exc)


def init_observability(app: Optional["FastAPI"] = None) -> None:  # noqa: F821
    """Setup logging & tracing. Call once at process start."""

    _setup_logging()
    _setup_tracing(app)

    logging.getLogger(__name__).info("Observability initialized")
