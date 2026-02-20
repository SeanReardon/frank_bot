"""
Utilities to load the OpenAPI document for the Actions HTTP API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import Settings


def _load_spec(path: Path, settings: Settings) -> dict[str, Any]:
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
        raise ValueError(
            f"Invalid JSON in OpenAPI file {path}: {exc}",
        ) from exc

    document["servers"] = [{"url": settings.public_base_url.rstrip("/")}]
    return document


def _resolve_spec_path(settings: Settings) -> Path:
    path = Path(settings.actions_openapi_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def load_openapi_document(settings: Settings) -> dict[str, Any]:
    """Load the canonical OpenAPI spec (all endpoints, proper REST)."""
    return _load_spec(_resolve_spec_path(settings), settings)


def load_openai_kludge_document(settings: Settings) -> dict[str, Any]:
    """
    Load the OpenAI-specific consolidated spec.

    OpenAI GPT Actions caps at 30 operations, so we consolidate related
    endpoint families into multiplexed "action" parameter endpoints.
    Falls back to the canonical spec if the kludge file doesn't exist.
    """
    kludge_path = _resolve_spec_path(settings).parent / "spec-openai.json"

    try:
        return _load_spec(kludge_path, settings)
    except FileNotFoundError:
        return load_openapi_document(settings)


# Legacy alias — kept in case anything still references it
load_chatgpt_openapi_document = load_openai_kludge_document


__all__ = [
    "load_openapi_document",
    "load_openai_kludge_document",
    "load_chatgpt_openapi_document",
]
