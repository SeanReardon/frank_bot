"""
Introspection module for Frank Bot meta documentation generation.

Generates Markdown documentation from FrankAPI by inspecting namespace
classes and their methods.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_type_hints

from meta.api import (
    AndroidNamespace,
    CalendarNamespace,
    ContactsNamespace,
    FrankAPI,
    SMSNamespace,
    SwarmNamespace,
    TelegramNamespace,
    TimeNamespace,
    UPSNamespace,
)


def _get_method_signature(method: Any) -> str:
    """Get a clean method signature string."""
    try:
        sig = inspect.signature(method)
        params = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue

            # Get type annotation
            type_hint = ""
            try:
                hints = get_type_hints(method)
                if name in hints:
                    hint = hints[name]
                    # Simplify type representation
                    if hasattr(hint, "__name__"):
                        type_hint = hint.__name__
                    elif hasattr(hint, "__origin__"):
                        # Handle generics like list[str]
                        origin = getattr(hint, "__origin__", None)
                        if origin:
                            type_hint = str(hint).replace("typing.", "")
                    else:
                        type_hint = str(hint).replace("typing.", "")
            except Exception:
                pass

            # Build parameter string
            if param.default is inspect.Parameter.empty:
                if param.kind == inspect.Parameter.KEYWORD_ONLY:
                    param_str = f"{name}: {type_hint}" if type_hint else name
                else:
                    param_str = f"{name}: {type_hint}" if type_hint else name
            else:
                default = repr(param.default)
                if type_hint:
                    param_str = f"{name}: {type_hint} = {default}"
                else:
                    param_str = f"{name}={default}"

            params.append(param_str)

        return f"({', '.join(params)})"
    except Exception:
        return "()"


def _extract_description(docstring: str | None) -> str:
    """Extract the first paragraph (description) from a docstring."""
    if not docstring:
        return ""

    # Get first paragraph
    lines = docstring.strip().split("\n")
    description_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            break
        # Stop at section headers
        if stripped.endswith(":") and stripped[:-1] in (
            "Parameters",
            "Args",
            "Returns",
            "Raises",
            "Example",
        ):
            break
        description_lines.append(stripped)

    return " ".join(description_lines)


def _get_namespace_methods(namespace_class: type) -> list[dict[str, str]]:
    """Get all public methods from a namespace class."""
    methods = []

    for name in dir(namespace_class):
        if name.startswith("_"):
            continue

        attr = getattr(namespace_class, name)
        if not callable(attr):
            continue

        method = attr
        signature = _get_method_signature(method)
        description = _extract_description(method.__doc__)

        methods.append(
            {
                "name": name,
                "signature": signature,
                "description": description,
            }
        )

    return methods


def generate_meta_documentation() -> str:
    """
    Generate Markdown documentation from FrankAPI.

    Returns:
        Markdown string documenting all FrankAPI namespaces and methods.
    """
    doc_parts = []

    # Header
    doc_parts.append("# FrankAPI Documentation\n")
    doc_parts.append(
        "FrankAPI provides synchronous access to Frank Bot capabilities "
        "for use in scripts.\n"
    )

    # Quick start example
    doc_parts.append("## Quick Start\n")
    doc_parts.append("```python")
    doc_parts.append('"""')
    doc_parts.append("Example script: Find restaurants visited with a companion.")
    doc_parts.append("")
    doc_parts.append("Parameters:")
    doc_parts.append("    companion (str): Name of the companion to filter by")
    doc_parts.append("    year (int): Year to search (default: current year)")
    doc_parts.append('"""')
    doc_parts.append("")
    doc_parts.append("def main(frank, companion, year=2024):")
    doc_parts.append("    # Search checkins for restaurants with companion")
    doc_parts.append("    result = frank.swarm.checkins(")
    doc_parts.append("        category='restaurant',")
    doc_parts.append("        with_companion=companion,")
    doc_parts.append("        year=year,")
    doc_parts.append("        max_results=50")
    doc_parts.append("    )")
    doc_parts.append("    ")
    doc_parts.append("    # Return just the venue names and dates")
    doc_parts.append("    return {")
    doc_parts.append("        'restaurants': [")
    doc_parts.append("            {")
    doc_parts.append("                'name': c['venue']['name'],")
    doc_parts.append("                'date': c['date']")
    doc_parts.append("            }")
    doc_parts.append("            for c in result.get('checkins', [])")
    doc_parts.append("        ]")
    doc_parts.append("    }")
    doc_parts.append("```\n")

    # Execution workflow
    doc_parts.append("## Execution Workflow\n")
    doc_parts.append(
        "Scripts are executed via the `/frank/execute` endpoint:\n"
    )
    doc_parts.append("1. **POST /frank/execute** with `slug`, `code`, and `params`")
    doc_parts.append("2. Server saves the script and starts execution in background")
    doc_parts.append("3. Response includes `job_id` with `status='running'`")
    doc_parts.append("4. **GET /frank/jobs/{job_id}** to poll for completion")
    doc_parts.append("5. When `status='completed'`, the `result` field contains the return value\n")
    doc_parts.append("For existing scripts, use `script_id` instead of `code`:\n")
    doc_parts.append("```json")
    doc_parts.append('{"script_id": "2024-01-15T10-30-00Z-find-restaurants", "params": {"companion": "Lauren"}}')
    doc_parts.append("```\n")

    # Namespace documentation
    namespaces = [
        ("calendar", CalendarNamespace, "Calendar operations (events, scheduling)"),
        ("contacts", ContactsNamespace, "Contact lookup and search"),
        ("sms", SMSNamespace, "SMS messaging"),
        ("swarm", SwarmNamespace, "Swarm/Foursquare check-in history"),
        ("ups", UPSNamespace, "UPS power status"),
        ("time", TimeNamespace, "Current time with timezone"),
        ("telegram", TelegramNamespace, "Telegram messaging via personal account"),
        ("android", AndroidNamespace, "Android phone automation (tasks)"),
    ]

    doc_parts.append("## Services\n")

    for namespace_name, namespace_class, description in namespaces:
        doc_parts.append(f"### frank.{namespace_name}\n")
        doc_parts.append(f"{description}\n")

        methods = _get_namespace_methods(namespace_class)

        if methods:
            doc_parts.append("| Method | Signature | Description |")
            doc_parts.append("|--------|-----------|-------------|")

            for method in methods:
                # Escape pipes in signature
                sig = method["signature"].replace("|", "\\|")
                desc = method["description"].replace("|", "\\|")
                doc_parts.append(f"| `{method['name']}` | `{sig}` | {desc} |")

            doc_parts.append("")

    # Footer
    doc_parts.append("## Notes\n")
    doc_parts.append("- All methods are synchronous and safe to use in scripts")
    doc_parts.append("- Scripts have a 10-minute timeout")
    doc_parts.append("- Use `print()` for debugging; output is captured in `stdout`")
    doc_parts.append("- Return a dict from `main()` for structured results")
    doc_parts.append("- Check `/frank/scripts` for existing reusable scripts")

    return "\n".join(doc_parts)


def generate_method_table(namespace_name: str, namespace_class: type) -> str:
    """
    Generate a Markdown table for a single namespace.

    Args:
        namespace_name: The name of the namespace (e.g., "calendar")
        namespace_class: The namespace class to document

    Returns:
        Markdown table string
    """
    methods = _get_namespace_methods(namespace_class)

    if not methods:
        return ""

    lines = [
        f"### frank.{namespace_name}\n",
        "| Method | Signature | Description |",
        "|--------|-----------|-------------|",
    ]

    for method in methods:
        sig = method["signature"].replace("|", "\\|")
        desc = method["description"].replace("|", "\\|")
        lines.append(f"| `{method['name']}` | `{sig}` | {desc} |")

    return "\n".join(lines)


__all__ = [
    "generate_meta_documentation",
    "generate_method_table",
]
