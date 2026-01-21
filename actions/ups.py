"""
UPS actions: query home UPS status.
"""

from __future__ import annotations

from typing import Any

from services.ups_status import get_ups_status


async def get_ups_status_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = arguments  # unused
    status = get_ups_status()
    return {
        "message": "UPS status placeholder until data source is wired.",
        "runtime": {
            "hours": status.runtime.hours,
            "mins": status.runtime.mins,
            "human": status.runtime.human,
        },
        "charge_percent": status.charge_percent,
        "temperature_f": status.temperature_f,
    }


__all__ = ["get_ups_status_action"]
