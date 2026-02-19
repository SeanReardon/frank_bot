"""
Google Calendar actions: get, create, update, delete events; get calendars.
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

CREATED_BY_PREFIX = "Created by Frank_Bot on behalf of"


def _created_by_tag() -> str:
    settings = get_settings()
    return f"\n\n{CREATED_BY_PREFIX} {settings.owner_name}"


def _is_owned_by_frank(event: dict[str, Any]) -> bool:
    """Return True if the event description contains the Frank_Bot tag."""
    desc = event.get("description") or ""
    return CREATED_BY_PREFIX in desc


def _require_ownership(event: dict[str, Any]) -> None:
    """Raise ValueError if frank_bot didn't create this event."""
    if not _is_owned_by_frank(event):
        summary = event.get("summary", "Untitled")
        raise ValueError(
            f"Cannot modify event '{summary}': Frank_Bot can "
            f"only update or delete events it created. "
            f"Look for \"{CREATED_BY_PREFIX}\" in the "
            f"event description to identify Frank_Bot events."
        )


async def get_events_action(
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


async def create_event_action(
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

    raw_description = args.get("description") or ""
    description = raw_description + _created_by_tag()
    location = args.get("location")
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


async def get_calendars_action(
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


async def update_event_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Update a calendar event that was created by Frank_Bot.

    Args:
        event_id: Google Calendar event ID (required)
        summary: New event title
        description: New event description (Frank_Bot tag is preserved)
        start: New start time (ISO 8601)
        end: New end time (ISO 8601)
        location: New location
        time_zone: Timezone for start/end
        calendar_id: Calendar ID (default: primary)
        calendar_name: Calendar name (fuzzy matched)
    """
    args = arguments or {}
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("'event_id' is required")

    settings = get_settings()
    time_zone = args.get("time_zone") or settings.default_timezone
    calendar_id_arg = args.get("calendar_id")
    calendar_name = args.get("calendar_name")

    def do_update():
        service = GoogleCalendarService()
        cal_id = service.resolve_calendar_id(
            calendar_id=calendar_id_arg,
            calendar_name=calendar_name,
        )

        event = service.get_event(event_id, calendar_id=cal_id)
        _require_ownership(event)

        updates: dict[str, Any] = {}
        if "summary" in args:
            updates["summary"] = args["summary"]
        if "start" in args:
            start_dt = parse_iso_datetime(args["start"])
            updates["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": time_zone,
            }
        if "end" in args:
            end_dt = parse_iso_datetime(args["end"])
            updates["end"] = {
                "dateTime": end_dt.isoformat(),
                "timeZone": time_zone,
            }
        if "location" in args:
            updates["location"] = args["location"]
        if "description" in args:
            new_desc = args["description"] or ""
            if CREATED_BY_PREFIX not in new_desc:
                new_desc = new_desc + _created_by_tag()
            updates["description"] = new_desc

        if not updates:
            raise ValueError(
                "No fields to update. Provide at least one of: "
                "summary, description, start, end, location."
            )

        return service.update_event(
            event_id, updates=updates, calendar_id=cal_id,
        ), cal_id

    updated_event, resolved_cal_id = await asyncio.to_thread(
        do_update,
    )
    calendar_label = (
        calendar_name or resolved_cal_id or "primary"
    )

    return {
        "message": (
            f"Updated event "
            f"'{updated_event.get('summary', '')}' "
            f"on calendar '{calendar_label}'"
        ),
        "event": updated_event,
        "calendar": {
            "id": resolved_cal_id or "primary",
            "label": calendar_label,
        },
    }


async def delete_event_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Delete a calendar event that was created by Frank_Bot.

    Args:
        event_id: Google Calendar event ID (required)
        calendar_id: Calendar ID (default: primary)
        calendar_name: Calendar name (fuzzy matched)
    """
    args = arguments or {}
    event_id = (args.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("'event_id' is required")

    calendar_id_arg = args.get("calendar_id")
    calendar_name = args.get("calendar_name")

    def do_delete():
        service = GoogleCalendarService()
        cal_id = service.resolve_calendar_id(
            calendar_id=calendar_id_arg,
            calendar_name=calendar_name,
        )

        event = service.get_event(event_id, calendar_id=cal_id)
        _require_ownership(event)
        event_summary = event.get("summary", "Untitled")

        service.delete_event(event_id, calendar_id=cal_id)
        return event_summary, cal_id

    summary, resolved_cal_id = await asyncio.to_thread(do_delete)
    calendar_label = (
        calendar_name or resolved_cal_id or "primary"
    )

    return {
        "message": (
            f"Deleted event '{summary}' "
            f"from calendar '{calendar_label}'"
        ),
        "event_id": event_id,
        "calendar": {
            "id": resolved_cal_id or "primary",
            "label": calendar_label,
        },
    }


__all__ = [
    "get_events_action",
    "create_event_action",
    "update_event_action",
    "delete_event_action",
    "get_calendars_action",
]
