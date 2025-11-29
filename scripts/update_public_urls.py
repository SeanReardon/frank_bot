#!/usr/bin/env python
"""
Utility to rewrite public-facing documents with the configured base URL.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://localhost:8000"


def main() -> None:
    base_url = (os.getenv("PUBLIC_BASE_URL") or DEFAULT_BASE).rstrip("/")
    openapi_path = ROOT / "openapi" / "spec.json"

    _update_openapi(openapi_path, base_url)

    print(f"Updated OpenAPI document with base URL {base_url}")


def _update_openapi(path: Path, base_url: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI file not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["servers"] = [{"url": base_url}]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
