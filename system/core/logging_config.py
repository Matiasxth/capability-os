"""Capability OS — Structured logging with daily rotation.

Logs to workspace/logs/capos_YYYY-MM-DD.log. Rotates daily, keeps 7 days.
Call setup_logging() once at startup.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(workspace_root: str | Path | None = None, level: str = "INFO") -> logging.Logger:
    """Configure root logger with file + console handlers."""
    root = logging.getLogger("capos")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers on re-init
    if root.handlers:
        return root

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Console handler (stdout)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler (daily rotation)
    if workspace_root:
        log_dir = Path(workspace_root) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "capos.log"
        try:
            file_handler = TimedRotatingFileHandler(
                str(log_file), when="midnight", backupCount=7,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            file_handler.suffix = "%Y-%m-%d"
            root.addHandler(file_handler)
        except Exception:
            pass  # Can't write logs — not fatal

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the capos namespace."""
    return logging.getLogger(f"capos.{name}")
