"""
Thermostat data normalization helpers.

The AndroidPhoneRunner returns whatever the vision model extracts. In practice,
different runs can emit different key shapes (e.g. `current_temperature` vs
`current_temp`, nested `setpoints`, degrees symbols, etc.). This module
converts those shapes into a stable schema for the thermostat actions.
"""

from __future__ import annotations

import re
from typing import Any


def _int_from_any(value: object) -> int | None:
    """
    Extract an integer from common thermostat text formats.

    Examples:
      "68°" -> 68
      "68°F" -> 68
      "68° (unit not explicitly shown; appears to be °F)" -> 68
      68 -> 68
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    s = str(value).strip()
    if not s:
        return None

    m = re.search(r"(-?\d{1,3})", s)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _mode_from_any(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    # Normalize separators
    s = s.replace("&", "and").replace("•", " ").replace("/", " ")
    s = " ".join(s.split())

    if "eco" in s:
        return "eco"
    if s in ("off", "system off"):
        return "off"
    if "heat" in s and "cool" in s:
        return "heat_cool"
    if "heat" in s:
        return "heat"
    if "cool" in s or "ac" in s:
        return "cool"
    return None


def _status_from_any(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    # In Google Home/Nest, "Maintaining X for heating and Y for cooling" is an
    # idle/steady-state message, not an indication that heat is actively running.
    if "maintaining" in s or "idle" in s:
        return "idle"
    if "heating" in s or "heating to" in s:
        return "heating"
    if "cooling" in s or "cooling to" in s:
        return "cooling"
    if "off" in s:
        return "off"
    return None


def _find_first(mapping: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in mapping and mapping[k] is not None:
            return mapping[k]
    return None


def normalize_get_status(extracted: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalize getStatus output into a stable schema.

    Output keys:
      - current_temp: int | None
      - target_low: int | None
      - target_high: int | None
      - mode: str | None  (heat|cool|heat_cool|eco|off)
      - humidity: int | None
      - status: str | None (heating|cooling|idle|off)

    Also includes:
      - device_name: str | None
      - raw: dict[str, Any] (original extracted payload)
    """
    raw: dict[str, Any] = extracted or {}
    if not isinstance(raw, dict):
        raw = {}

    # Allow nested setpoints shape.
    setpoints = raw.get("setpoints")
    if not isinstance(setpoints, dict):
        setpoints = {}

    current_val = _find_first(
        raw,
        "current_temp",
        "current_temperature",
        "currentTemperature",
        "current temp (with unit)",
        "current temp",
    )
    heat_val = _find_first(
        raw,
        "target_low",
        "heat_setpoint",
        "heat setpoint (with unit)",
        "heat setpoint",
    )
    cool_val = _find_first(
        raw,
        "target_high",
        "cool_setpoint",
        "cool setpoint (with unit)",
        "cool setpoint",
    )
    if heat_val is None:
        heat_val = _find_first(setpoints, "heat_setpoint", "heat", "low", "min")
    if cool_val is None:
        cool_val = _find_first(setpoints, "cool_setpoint", "cool", "high", "max")

    humidity_val = _find_first(raw, "humidity", "indoor_humidity", "humidity_percent")
    if humidity_val is None:
        additional = raw.get("additional_readings")
        if isinstance(additional, dict):
            humidity_val = _find_first(additional, "indoor_humidity", "humidity")

    mode_val = _find_first(raw, "mode", "hvac_mode", "thermostat_mode")
    status_val = _find_first(
        raw,
        "status",
        "status_text",
        "hvac_status",
        "hvac_status_text",
    )
    device_name = _find_first(raw, "device_name", "thermostat_device_name", "thermostat/device name")

    normalized = {
        "current_temp": _int_from_any(current_val),
        "target_low": _int_from_any(heat_val),
        "target_high": _int_from_any(cool_val),
        "mode": _mode_from_any(mode_val),
        "humidity": _int_from_any(humidity_val),
        "status": _status_from_any(status_val),
        "device_name": str(device_name).strip() if device_name is not None else None,
        "raw": raw,
    }

    return normalized


def normalize_set_range(extracted: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize setRange output into {final_low_temp, final_high_temp, mode, raw}."""
    raw: dict[str, Any] = extracted or {}
    if not isinstance(raw, dict):
        raw = {}

    low = _find_first(raw, "final_low_temp", "low_temp", "target_low", "heat_setpoint")
    high = _find_first(raw, "final_high_temp", "high_temp", "target_high", "cool_setpoint")
    mode = _find_first(raw, "mode", "hvac_mode")

    return {
        "final_low_temp": _int_from_any(low),
        "final_high_temp": _int_from_any(high),
        "mode": _mode_from_any(mode),
        "raw": raw,
    }


__all__ = ["normalize_get_status", "normalize_set_range"]

