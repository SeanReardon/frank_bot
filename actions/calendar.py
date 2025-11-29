"""
Google Calendar actions: list events, create events, list calendars.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any

from actions.helpers import (
    coerce_bool,
    coerce_int,
    format_datetime,
    parse_iso_datetime,
    resolve_timezone,
)
from config import get_settings
from services.google_calendar import GoogleCalendarService
from services.google_contacts import GoogleContactsService

logger = logging.getLogger(__name__)


async def list_calendar_events_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    settings = get_settings()
    max_results = coerce_int(
        args.get("max_results"),
        10,
        minimum=1,
        maximum=50,
    )

    tz_name = args.get("time_zone") or settings.default_timezone
    tzinfo = resolve_timezone(tz_name)

    day_str = args.get("day")
    time_min = args.get("time_min")
    time_max = args.get("time_max")
    calendar_id_arg = args.get("calendar_id")
    calendar_name = args.get("calendar_name")
    resolved_calendar_id: str | None = None

    if day_str:
        try:
            target_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(
                "day must be provided in YYYY-MM-DD format"
            ) from exc
        start_dt = datetime.combine(target_day, dt_time.min, tzinfo=tzinfo)
        end_dt = start_dt + timedelta(days=1)
        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()
    elif not time_min and not time_max:
        today = datetime.now(tzinfo).date()
        start_dt = datetime.combine(today, dt_time.min, tzinfo=tzinfo)
        end_dt = start_dt + timedelta(days=1)
        time_min = start_dt.isoformat()
        time_max = end_dt.isoformat()

    def fetch_events():
        nonlocal resolved_calendar_id
        service = GoogleCalendarService()
        resolved_calendar_id = service.resolve_calendar_id(
            calendar_id=calendar_id_arg,
            calendar_name=calendar_name,
        )
        return service.list_upcoming_events(
            max_results=max_results,
            time_min=time_min,
            time_max=time_max,
            calendar_id=resolved_calendar_id,
        )

    events = await asyncio.to_thread(fetch_events)
    calendar_label = (
        calendar_name
        or calendar_id_arg
        or resolved_calendar_id
        or "primary"
    )

    if not events:
        summary_range = f"{time_min or 'now'} to {time_max or 'open-ended'}"
        message = (
            f"No calendar events scheduled between {summary_range} "
            f"on calendar '{calendar_label}'."
        )
    else:
        lines = [f"Found {len(events)} event(s) on '{calendar_label}':"]
        for event in events:
            start_info = event.get("start", {})
            raw_start = start_info.get(
                "dateTime",
                start_info.get("date", "unknown time"),
            )
            start_str = (
                format_datetime(raw_start)
                if raw_start and "T" in raw_start
                else raw_start
            )
            summary = event.get("summary", "No title")
            location = event.get("location")
            line = f"- {start_str}: {summary}"
            if location:
                line += f" @ {location}"
            lines.append(line)
        message = "\n".join(lines)

    return {
        "message": message,
        "calendar": {
            "id": resolved_calendar_id or calendar_id_arg or "primary",
            "label": calendar_label,
        },
        "time_window": {
            "time_min": time_min,
            "time_max": time_max,
            "time_zone": tz_name,
        },
        "count": len(events),
        "events": events,
    }


async def create_calendar_event_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    try:
        summary = args["summary"]
        start_raw = args["start"]
        end_raw = args["end"]
    except KeyError as exc:
        raise ValueError(
            "summary, start, and end are required to create an event."
        ) from exc

    attendees_raw = args.get("attendees") or []
    if isinstance(attendees_raw, str):
        attendees_list = [attendees_raw]
    else:
        attendees_list = list(attendees_raw)
    attendees_clean = [
        email.strip()
        for email in attendees_list
        if isinstance(email, str) and email.strip()
    ]

    description = args.get("description")
    location = args.get("location")  # Simple string like "Nerdvana, Frisco, TX"
    settings = get_settings()
    time_zone = args.get("time_zone") or settings.default_timezone
    calendar_id_arg = args.get("calendar_id")
    calendar_name = args.get("calendar_name")
    resolved_calendar_id: str | None = None

    def validate_attendees():
        missing: list[str] = []
        if attendees_clean:
            contacts_service = GoogleContactsService()
            for email in attendees_clean:
                if not contacts_service.contact_exists(email):
                    missing.append(email)
        return missing

    missing = await asyncio.to_thread(validate_attendees)
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(
            "The following attendee emails are not in your contacts: "
            f"{missing_str}"
        )

    def create_event():
        nonlocal resolved_calendar_id
        service = GoogleCalendarService()
        resolved_calendar_id = service.resolve_calendar_id(
            calendar_id=calendar_id_arg,
            calendar_name=calendar_name,
        )
        start_dt = parse_iso_datetime(start_raw)
        end_dt = parse_iso_datetime(end_raw)
        extra_fields: dict[str, Any] = {}

        if attendees_clean:
            extra_fields["attendees"] = [
                {"email": email}
                for email in attendees_clean
            ]

        if location:
            extra_fields["location"] = location

        created = service.create_event(
            summary=summary,
            description=description,
            start_time=start_dt,
            end_time=end_dt,
            time_zone=time_zone,
            extra_fields=extra_fields or None,
            calendar_id=resolved_calendar_id,
        )
        return created

    created_event = await asyncio.to_thread(create_event)
    start_desc = (
        created_event.get("start", {}).get("dateTime")
        or created_event.get("start")
    )
    end_desc = (
        created_event.get("end", {}).get("dateTime")
        or created_event.get("end")
    )
    calendar_label = calendar_name or resolved_calendar_id or "primary"
    location_desc = created_event.get("location")
    message = (
        f"Created event '{created_event.get('summary', summary)}' "
        f"from {start_desc} to {end_desc} "
        f"on calendar '{calendar_label}'"
    )
    if location_desc:
        message += f" at {location_desc}"

    return {
        "message": message,
        "event": created_event,
        "calendar": {
            "id": resolved_calendar_id or calendar_id_arg or "primary",
            "label": calendar_label,
        },
    }


async def list_calendars_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    include_access_role = coerce_bool(args.get("include_access_role"))
    primary_only = coerce_bool(args.get("primary_only"))

    def fetch_calendars():
        service = GoogleCalendarService()
        calendars = service.list_calendars()
        if primary_only:
            calendars = [
                cal for cal in calendars if cal.get("primary") is True
            ]
        results = []
        for cal in calendars:
            entry = {
                "id": cal.get("id"),
                "summary": cal.get("summary"),
                "timeZone": cal.get("timeZone"),
                "primary": cal.get("primary", False),
            }
            if include_access_role:
                entry["accessRole"] = cal.get("accessRole")
            results.append(entry)
        return results

    calendars = await asyncio.to_thread(fetch_calendars)
    if not calendars:
        text = "No calendars were returned for this account."
    else:
        lines = ["Available calendars:"]
        for cal in calendars:
            summary = cal.get("summary") or "Unnamed"
            cal_id = cal.get("id") or "unknown id"
            tz = cal.get("timeZone") or "unknown tz"
            role = cal.get("accessRole") or "n/a"
            if include_access_role:
                lines.append(
                    f"- {summary} (id={cal_id}, tz={tz}, role={role})"
                )
            else:
                lines.append(f"- {summary} (id={cal_id}, tz={tz})")
        text = "\n".join(lines)

    return {
        "message": text,
        "count": len(calendars),
        "calendars": calendars,
    }


__all__ = [
    "list_calendar_events_action",
    "create_calendar_event_action",
    "list_calendars_action",
]
