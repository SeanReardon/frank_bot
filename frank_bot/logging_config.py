"""
Logging utilities shared across the application.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def configure_logging(log_file: str, log_level: str) -> None:
    """Configure root logging handlers and formatters."""
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - "
        "[%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    level = getattr(logging, log_level.upper(), logging.DEBUG)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Expand ~ to home directory and ensure parent directory exists
    expanded_log_file = os.path.expanduser(log_file)
    log_path = Path(expanded_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(expanded_log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Log where we're writing to (helps debug path issues)
    root_logger.info("Logging to file: %s", expanded_log_file)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).setLevel(logging.INFO)

