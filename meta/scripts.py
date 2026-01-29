"""
Script storage and parsing utilities for Frank Bot meta module.

Scripts are stored as .py files in ./data/scripts/ directory with filenames
following the pattern: {ISO8601-timestamp}-{slug}.py

Docstrings are parsed to extract metadata:
- description: First paragraph of docstring
- parameters: From "Parameters:" section
- example: From "Example:" section
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default scripts directory - uses DATA_DIR env var if set (for Docker),
# otherwise falls back to relative path from project root
_data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
DEFAULT_SCRIPTS_DIR = Path(_data_dir) / "scripts"


@dataclass
class ScriptParameter:
    """Represents a script parameter parsed from docstring."""

    name: str
    type: str | None
    description: str


@dataclass
class ScriptMetadata:
    """Metadata extracted from a script's docstring."""

    id: str
    slug: str
    description: str
    parameters: list[ScriptParameter]
    example: str | None
    created_at: str


def parse_docstring(docstring: str | None) -> dict[str, Any]:
    """
    Parse a script docstring to extract metadata.

    Args:
        docstring: The raw docstring to parse

    Returns:
        Dict with keys: description, parameters, example
    """
    if not docstring:
        return {"description": "", "parameters": [], "example": None}

    lines = docstring.strip().split("\n")

    # Extract description (first paragraph - up to first blank line or section)
    description_lines = []
    i = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            break
        # Stop at section headers
        if stripped.endswith(":") and stripped[:-1] in (
            "Parameters",
            "Args",
            "Example",
            "Returns",
            "Raises",
        ):
            break
        description_lines.append(stripped)

    description = " ".join(description_lines)

    # Find sections
    parameters: list[ScriptParameter] = []
    example: str | None = None

    current_section: str | None = None
    section_lines: list[str] = []

    for line in lines[i:]:
        stripped = line.strip()

        # Check for section headers
        if stripped in ("Parameters:", "Args:"):
            current_section = "parameters"
            section_lines = []
            continue
        elif stripped == "Example:":
            current_section = "example"
            section_lines = []
            continue
        elif stripped in ("Returns:", "Raises:"):
            # End previous section
            if current_section == "example" and section_lines:
                example = "\n".join(section_lines).strip()
            current_section = None
            section_lines = []
            continue

        # Collect section content
        if current_section:
            section_lines.append(line.rstrip())

    # Process final section
    if current_section == "example" and section_lines:
        example = "\n".join(section_lines).strip()

    # Parse parameters section
    if current_section == "parameters" or any(
        line.strip() in ("Parameters:", "Args:") for line in lines
    ):
        # Re-find parameters section
        in_params = False
        param_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in ("Parameters:", "Args:"):
                in_params = True
                continue
            elif (
                in_params
                and stripped.endswith(":")
                and stripped[:-1] in ("Example", "Returns", "Raises")
            ):
                break
            elif in_params:
                param_lines.append(line)

        parameters = _parse_parameters_section(param_lines)

    return {
        "description": description,
        "parameters": parameters,
        "example": example,
    }


def _parse_parameters_section(lines: list[str]) -> list[ScriptParameter]:
    """Parse the Parameters: section of a docstring."""
    parameters: list[ScriptParameter] = []

    # Pattern: param_name (type): description
    # or: param_name: description
    param_pattern = re.compile(r"^\s*(\w+)(?:\s*\(([^)]+)\))?:\s*(.*)$")

    current_param: ScriptParameter | None = None
    current_desc_lines: list[str] = []

    for line in lines:
        if not line.strip():
            continue

        match = param_pattern.match(line)
        if match:
            # Save previous parameter
            if current_param:
                if current_desc_lines:
                    current_param = ScriptParameter(
                        name=current_param.name,
                        type=current_param.type,
                        description=" ".join(
                            [current_param.description] + current_desc_lines
                        ).strip(),
                    )
                parameters.append(current_param)

            # Start new parameter
            name, type_hint, desc = match.groups()
            current_param = ScriptParameter(
                name=name,
                type=type_hint,
                description=desc.strip(),
            )
            current_desc_lines = []
        elif current_param and line.strip():
            # Continuation of description
            current_desc_lines.append(line.strip())

    # Don't forget the last parameter
    if current_param:
        if current_desc_lines:
            current_param = ScriptParameter(
                name=current_param.name,
                type=current_param.type,
                description=" ".join(
                    [current_param.description] + current_desc_lines
                ).strip(),
            )
        parameters.append(current_param)

    return parameters


def get_script_docstring(code: str) -> str | None:
    """Extract the module docstring from Python code."""
    try:
        tree = ast.parse(code)
        return ast.get_docstring(tree)
    except SyntaxError:
        return None


def parse_script_filename(filename: str) -> tuple[str, str] | None:
    """
    Parse a script filename to extract timestamp and slug.

    Expected format: {ISO8601-timestamp}-{slug}.py
    Example: 2024-01-15T10-30-00Z-my-script.py

    Returns:
        Tuple of (timestamp, slug) or None if invalid format
    """
    if not filename.endswith(".py"):
        return None

    name = filename[:-3]  # Remove .py

    # ISO8601 timestamp pattern (with dashes in time to be filesystem-safe)
    # Format: YYYY-MM-DDTHH-MM-SSZ
    pattern = r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-(.+)$"
    match = re.match(pattern, name)
    if match:
        timestamp, slug = match.groups()
        return timestamp, slug

    return None


def generate_script_filename(slug: str, timestamp: datetime | None = None) -> str:
    """
    Generate a script filename from a slug and optional timestamp.

    Args:
        slug: The script slug (e.g., "my-script")
        timestamp: Optional datetime, defaults to now (UTC)

    Returns:
        Filename in format: {ISO8601-timestamp}-{slug}.py
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Format timestamp as filesystem-safe ISO8601 (replace : with -)
    ts_str = timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"{ts_str}-{slug}.py"


def list_scripts(
    scripts_dir: Path | str | None = None,
) -> list[ScriptMetadata]:
    """
    List all scripts with their metadata.

    Args:
        scripts_dir: Directory containing scripts (defaults to ./data/scripts/)

    Returns:
        List of ScriptMetadata objects sorted by created_at (newest first)
    """
    if scripts_dir is None:
        scripts_dir = DEFAULT_SCRIPTS_DIR
    else:
        scripts_dir = Path(scripts_dir)

    if not scripts_dir.exists():
        return []

    scripts: list[ScriptMetadata] = []

    for filename in os.listdir(scripts_dir):
        parsed = parse_script_filename(filename)
        if parsed is None:
            continue

        timestamp, slug = parsed
        filepath = scripts_dir / filename

        try:
            code = filepath.read_text(encoding="utf-8")
            docstring = get_script_docstring(code)
            parsed_doc = parse_docstring(docstring)

            # Convert timestamp to ISO 8601 format
            created_at = timestamp.replace("T", "T").replace("-", "-")
            # Actually convert the filesystem-safe format back to standard ISO 8601
            # From: 2024-01-15T10-30-00Z to 2024-01-15T10:30:00Z
            parts = timestamp.split("T")
            if len(parts) == 2:
                date_part = parts[0]
                time_part = parts[1].replace("-", ":")
                created_at = f"{date_part}T{time_part}"

            scripts.append(
                ScriptMetadata(
                    id=filename[:-3],  # Remove .py for ID
                    slug=slug,
                    description=parsed_doc["description"],
                    parameters=[
                        ScriptParameter(
                            name=p.name,
                            type=p.type,
                            description=p.description,
                        )
                        for p in parsed_doc["parameters"]
                    ],
                    example=parsed_doc["example"],
                    created_at=created_at,
                )
            )
        except (OSError, UnicodeDecodeError):
            continue

    # Sort by created_at descending (newest first)
    scripts.sort(key=lambda s: s.created_at, reverse=True)
    return scripts


def get_script(
    script_id: str,
    scripts_dir: Path | str | None = None,
) -> str | None:
    """
    Get a script's code by ID.

    Args:
        script_id: The script ID (filename without .py extension)
        scripts_dir: Directory containing scripts (defaults to ./data/scripts/)

    Returns:
        The script's source code, or None if not found
    """
    if scripts_dir is None:
        scripts_dir = DEFAULT_SCRIPTS_DIR
    else:
        scripts_dir = Path(scripts_dir)

    filepath = scripts_dir / f"{script_id}.py"

    if not filepath.exists():
        return None

    try:
        return filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def save_script(
    slug: str,
    code: str,
    scripts_dir: Path | str | None = None,
    timestamp: datetime | None = None,
) -> str:
    """
    Save a new script.

    Args:
        slug: The script slug (e.g., "my-script")
        code: The Python source code
        scripts_dir: Directory to save scripts (defaults to ./data/scripts/)
        timestamp: Optional timestamp (defaults to now UTC)

    Returns:
        The script ID (filename without .py extension)
    """
    if scripts_dir is None:
        scripts_dir = DEFAULT_SCRIPTS_DIR
    else:
        scripts_dir = Path(scripts_dir)

    # Ensure directory exists
    scripts_dir.mkdir(parents=True, exist_ok=True)

    filename = generate_script_filename(slug, timestamp)
    filepath = scripts_dir / filename

    filepath.write_text(code, encoding="utf-8")

    return filename[:-3]  # Return ID (filename without .py)


def script_metadata_to_dict(metadata: ScriptMetadata) -> dict[str, Any]:
    """Convert ScriptMetadata to a JSON-serializable dict."""
    return {
        "id": metadata.id,
        "slug": metadata.slug,
        "description": metadata.description,
        "parameters": [
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
            }
            for p in metadata.parameters
        ],
        "example": metadata.example,
        "created_at": metadata.created_at,
    }


__all__ = [
    "ScriptParameter",
    "ScriptMetadata",
    "parse_docstring",
    "get_script_docstring",
    "parse_script_filename",
    "generate_script_filename",
    "list_scripts",
    "get_script",
    "save_script",
    "script_metadata_to_dict",
    "DEFAULT_SCRIPTS_DIR",
]
