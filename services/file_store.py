from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def derive_json_storage_dir(path_hint: str | None, default_dir: str) -> Path:
    """Derive a directory-backed JSON store location from a legacy path hint."""
    if not path_hint:
        return Path(default_dir)

    candidate = Path(path_hint)
    if candidate.suffix in {".db", ".json"}:
        return candidate.with_suffix("")
    return candidate


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def list_json_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        (child for child in path.iterdir() if child.is_file() and child.suffix == ".json"),
        key=lambda child: child.name,
    )


async def to_thread(func, /, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def newest_first(paths: Iterable[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: path.name, reverse=True)
