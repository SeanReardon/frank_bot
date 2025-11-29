"""
System-related actions: hello world, time, server info.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from actions.helpers import resolve_timezone
from config import get_settings
from services.ntp_time import fetch_utc_now
from services.swarm_service import SwarmService, describe_checkin

logger = logging.getLogger(__name__)

SERVER_START_TIME = datetime.now(timezone.utc)


async def hello_world_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    name = (args.get("name") or "world").strip() or "world"
    message = f"hello {name}"
    return {"message": message, "name": name}


async def get_my_time_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = arguments  # unused
    settings = get_settings()

    snapshot = await asyncio.to_thread(_fetch_swarm_time_snapshot)
    if snapshot:
        utc_now = await asyncio.to_thread(fetch_utc_now)
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)
        local_now = utc_now.astimezone(snapshot["tzinfo"])
        location_phrase = snapshot["location_summary"]
        if location_phrase:
            message = (
                "Derived from your latest Swarm check-in"
                f"{location_phrase}."
            )
        else:
            message = "Derived from your latest Swarm check-in."
        return {
            "message": message,
            "iso_time": local_now.isoformat(),
            "timezone": snapshot["timezone_label"],
            "offset_minutes": snapshot["offset_minutes"],
        }

    tzinfo = resolve_timezone(settings.default_timezone)
    now = datetime.now(tzinfo)
    offset_minutes = int(now.utcoffset().total_seconds() // 60)
    message = (
        "Using your configured DEFAULT_TIMEZONE "
        f"({settings.default_timezone})."
    )
    return {
        "message": message,
        "iso_time": now.isoformat(),
        "timezone": settings.default_timezone,
        "offset_minutes": offset_minutes,
    }


async def get_server_start_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = arguments  # unused
    now = datetime.now(timezone.utc)
    uptime = now - SERVER_START_TIME
    return {
        "message": "Docker instance start time.",
        "startup_iso_time": SERVER_START_TIME.isoformat(),
        "uptime_seconds": int(uptime.total_seconds()),
    }


def _fetch_swarm_time_snapshot() -> dict[str, Any] | None:
    """Return current time info derived from the latest Swarm check-in."""
    try:
        service = SwarmService()
    except ValueError:
        return None
    except Exception:
        logger.warning("Unable to initialize SwarmService", exc_info=True)
        return None

    try:
        checkins = service.get_self_checkins(limit=1)
    except Exception:
        logger.warning(
            "Swarm API error while fetching check-ins",
            exc_info=True,
        )
        return None

    if not checkins:
        return None

    checkin = checkins[0]
    offset = checkin.get("timeZoneOffset")
    if not isinstance(offset, int):
        return None

    info = describe_checkin(checkin)
    offset_delta = timedelta(minutes=offset)
    tz = timezone(offset_delta)

    venue = checkin.get("venue") or {}
    venue_name = venue.get("name")
    location = venue.get("location") or {}
    city = location.get("city")
    state = location.get("state")
    country = location.get("country")
    parts = [part for part in (venue_name, city, state, country) if part]
    summary = " at " + ", ".join(parts) if parts else ""

    return {
        "tzinfo": tz,
        "offset_minutes": offset,
        "timezone_label": _format_offset_label(offset),
        "location_summary": summary or "",
        "minutes_since": info.get("minutes_since"),
    }


def _format_offset_label(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    total = abs(minutes)
    hours, mins = divmod(total, 60)
    return f"UTC{sign}{hours:02d}:{mins:02d}"


__all__ = [
    "hello_world_action",
    "get_my_time_action",
    "get_server_start_action",
]
