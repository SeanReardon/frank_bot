from __future__ import annotations

from typing import Any

from services.task_classes import FREEFORM_TASK_CLASS


def get_task_runtime_profile(task_class: str | None) -> dict[str, Any]:
    normalized = (
        str(task_class or FREEFORM_TASK_CLASS).strip()
        or FREEFORM_TASK_CLASS
    )

    profiles: dict[str, dict[str, Any]] = {
        "android_capture": {
            "mode": "structured",
            "guarantees": [
                (
                    "Prefer START_ANDROID_TASK/POLL_ANDROID_TASK over "
                    "freeform shelling."
                ),
                "Return artifact paths and a short observation summary.",
                "Avoid unnecessary device mutations while capturing evidence.",
            ],
            "plan_lines": [
                "Task profile: android_capture.",
                (
                    "Primary goal: capture or inspect Android state with "
                    "durable artifacts."
                ),
                "Prefer Android task actions and poll until artifacts are ready.",
            ],
        },
        "calendar_edit": {
            "mode": "structured",
            "guarantees": [
                (
                    "Prefer calendar actions or structured scripts over ad hoc "
                    "reasoning."
                ),
                "State the intended calendar change clearly before applying it.",
            ],
            "plan_lines": [
                "Task profile: calendar_edit.",
                "Primary goal: inspect or modify calendar state predictably.",
            ],
        },
        "contact_lookup": {
            "mode": "structured",
            "guarantees": [
                "Prefer structured contact lookup tools.",
                "Return normalized identifiers when available.",
            ],
            "plan_lines": [
                "Task profile: contact_lookup.",
                (
                    "Primary goal: resolve a person and return trustworthy "
                    "contact details."
                ),
            ],
        },
        "message_draft": {
            "mode": "structured",
            "guarantees": [
                (
                    "Draft first; avoid sending unless the user clearly asked "
                    "to send."
                ),
                (
                    "Return concise candidate wording when a final send is "
                    "not required."
                ),
            ],
            "plan_lines": [
                "Task profile: message_draft.",
                (
                    "Primary goal: compose a message safely before any "
                    "transport action."
                ),
            ],
        },
        "diagnostic_probe": {
            "mode": "structured",
            "guarantees": [
                "Collect evidence before proposing fixes.",
                (
                    "Prefer traces, diagnostics, and operator/debug state for "
                    "root cause analysis."
                ),
            ],
            "plan_lines": [
                "Task profile: diagnostic_probe.",
                (
                    "Primary goal: gather evidence, explain likely cause, and "
                    "report next steps."
                ),
            ],
        },
        FREEFORM_TASK_CLASS: {
            "mode": "freeform",
            "guarantees": [],
            "plan_lines": [],
        },
    }

    return profiles.get(
        normalized,
        profiles[FREEFORM_TASK_CLASS],
    )
