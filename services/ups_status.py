"""
UPS status retrieval helpers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpsRuntime:
    hours: int
    mins: int
    human: str


@dataclass(frozen=True)
class UpsStatus:
    runtime: UpsRuntime
    charge_percent: int
    temperature_f: float


def _format_runtime(hours: int, mins: int) -> str:
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)


def build_runtime(hours: int, mins: int) -> UpsRuntime:
    return UpsRuntime(
        hours=hours,
        mins=mins,
        human=_format_runtime(hours, mins),
    )


def get_ups_status() -> UpsStatus:
    """
    Return the latest UPS status.

    Placeholder implementation until data source wiring is added.
    """
    runtime = build_runtime(0, 0)
    return UpsStatus(
        runtime=runtime,
        charge_percent=0,
        temperature_f=0asddasd.0,
    )


__all__ = ["UpsRuntime", "UpsStatus", "get_ups_status", "build_runtime"]
