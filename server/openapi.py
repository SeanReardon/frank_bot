"""
Utilities to load the OpenAPI document for the Actions HTTP API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import Settings


def load_openapi_document(settings: Settings) -> dict[str, Any]:
    """
    Load the OpenAPI JSON document from disk.
    """

    path = Path(settings.actions_openapi_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"OpenAPI file not found at {path}. "
            "Set ACTIONS_OPENAPI_PATH to the correct location."
        ) from exc

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise ValueError(f"Invalid JSON in OpenAPI file {path}: {exc}") from exc
    document["servers"] = [{"url": settings.public_base_url.rstrip("/")}]
    return document


def load_chatgpt_openapi_document(settings: Settings) -> dict[str, Any]:
    """
    Load the ChatGPT-specific OpenAPI JSON document from disk.

    This is a trimmed version of the full spec with only essential operations
    (under 30) to stay within ChatGPT's action limits.
    """
    # ChatGPT spec is always alongside the main spec
    main_path = Path(settings.actions_openapi_path).expanduser()
    if not main_path.is_absolute():
        main_path = (Path.cwd() / main_path).resolve()

    chatgpt_path = main_path.parent / "spec-chatgpt.json"

    try:
        raw = chatgpt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Fall back to full spec if ChatGPT-specific doesn't exist
        return load_openapi_document(settings)

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise ValueError(f"Invalid JSON in ChatGPT OpenAPI file {chatgpt_path}: {exc}") from exc

    document["servers"] = [{"url": settings.public_base_url.rstrip("/")}]
    return document


__all__ = ["load_openapi_document", "load_chatgpt_openapi_document"]

