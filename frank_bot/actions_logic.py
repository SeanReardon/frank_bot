"""
Shared business logic used by both the MCP server and REST Actions.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from frank_bot.config import get_settings
from frank_bot.services.google_calendar import GoogleCalendarService
from frank_bot.services.google_contacts import GoogleContactsService
from frank_bot.services.ntp_time import fetch_utc_now
from frank_bot.services.swarm_service import (
    SwarmService,
    describe_checkin,
)

logger = logging.getLogger(__name__)


def _resolve_timezone(name: str) -> ZoneInfo:
    """Return a ZoneInfo instance, falling back to UTC when needed."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone '%s'; falling back to UTC", name)
        return ZoneInfo("UTC")


def _format_datetime(value: str) -> str:
    """Best-effort ISO8601 formatter for human readability."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _parse_iso_datetime(value: str) -> datetime:
    """Parse ISO8601 datetimes while allowing trailing Z."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO8601 datetime: {value}") from exc


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(
    value: Any,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        converted = int(value)
    except (TypeError, ValueError):
        converted = default
    if minimum is not None:
        converted = max(minimum, converted)
    if maximum is not None:
        converted = min(maximum, converted)
    return converted


async def hello_world_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    name = (args.get("name") or "world").strip() or "world"
    message = f"hello {name}"
    return {"message": message, "name": name}


async def list_calendar_events_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    settings = get_settings()
    max_results = _coerce_int(
        args.get("max_results"),
        10,
        minimum=1,
        maximum=50,
    )

    tz_name = args.get("time_zone") or settings.default_timezone
    tzinfo = _resolve_timezone(tz_name)

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
                _format_datetime(raw_start)
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


async def search_contacts_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required to search contacts.")

    max_results = _coerce_int(
        args.get("max_results"),
        10,
        minimum=1,
        maximum=50,
    )

    def fetch_contacts():
        service = GoogleContactsService()
        results = service.search_contacts(query=query)
        return results[:max_results]

    contacts_raw = await asyncio.to_thread(fetch_contacts)
    contacts: list[dict[str, Any]] = []
    for person in contacts_raw:
        names = person.get("names") or []
        display_name = "Unnamed contact"
        for name in names:
            if name.get("displayName"):
                display_name = name["displayName"]
                break

        emails = [
            email.get("value")
            for email in person.get("emailAddresses") or []
            if email.get("value")
        ]
        phones = [
            phone.get("value")
            for phone in person.get("phoneNumbers") or []
            if phone.get("value")
        ]

        contacts.append(
            {
                "resource_name": person.get("resourceName"),
                "display_name": display_name,
                "emails": emails,
                "phones": phones,
            }
        )

    if not contacts:
        message = f"No contacts matched '{query}'."
    else:
        lines = [f"Top {len(contacts)} contact match(es) for '{query}':"]
        for contact in contacts:
            details = []
            if contact["emails"]:
                details.append("Emails: " + ", ".join(contact["emails"]))
            if contact["phones"]:
                details.append("Phones: " + ", ".join(contact["phones"]))
            suffix = f" ({'; '.join(details)})" if details else ""
            lines.append(f"- {contact['display_name']}{suffix}")
        message = "\n".join(lines)

    return {
        "message": message,
        "query": query,
        "count": len(contacts),
        "contacts": contacts,
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
        start_dt = _parse_iso_datetime(start_raw)
        end_dt = _parse_iso_datetime(end_raw)
        extra_fields: dict[str, Any] = {}

        if attendees_clean:
            extra_fields["attendees"] = [
                {"email": email}
                for email in attendees_clean
            ]

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
    message = (
        f"Created event '{created_event.get('summary', summary)}' "
        f"from {start_desc} to {end_desc} "
        f"on calendar '{calendar_label}'"
    )

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
    include_access_role = _coerce_bool(args.get("include_access_role"))
    primary_only = _coerce_bool(args.get("primary_only"))

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


async def list_my_swarm_checkins_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    List your Swarm check-ins with optional filtering.

    Supports:
    - Date range filtering (year, or specific start/end dates)
    - Filtering by companions (people you checked in with)
    - Category filtering

    Examples:
    - "What restaurants did I go to with Linda in 2024?"
    - "Where did Jimmy and I check in together?"
    - "Show my check-ins from last month"
    """
    args = arguments or {}
    max_results = _coerce_int(
        args.get("max_results"),
        10,
        minimum=1,
        maximum=250,
    )
    stale_minutes = _coerce_int(
        args.get("stale_minutes"),
        180,
        minimum=5,
        maximum=1440,
    )

    # Date filtering
    year = args.get("year")
    after_date = args.get("after_date")  # ISO date string YYYY-MM-DD
    before_date = args.get("before_date")  # ISO date string YYYY-MM-DD

    # Companion filtering - can be a single name or list of names
    with_companion = args.get("with_companion")  # Filter to only checkins with someone
    companion_names: list[str] = []
    if with_companion:
        if isinstance(with_companion, str):
            companion_names = [with_companion.strip().lower()]
        else:
            companion_names = [name.strip().lower() for name in with_companion if name]

    # If only_with_companions is true, filter to only checkins that have companions
    only_with_companions = _coerce_bool(args.get("only_with_companions"))

    # Category filtering
    category_filter = (args.get("category") or "").strip().lower()

    # Build timestamp filters
    after_timestamp: int | None = None
    before_timestamp: int | None = None

    if year:
        try:
            year_int = int(year)
            after_timestamp = int(datetime(year_int, 1, 1).timestamp())
            before_timestamp = int(datetime(year_int, 12, 31, 23, 59, 59).timestamp())
        except (ValueError, TypeError):
            raise ValueError(f"Invalid year: {year}")

    if after_date:
        try:
            dt = datetime.strptime(after_date, "%Y-%m-%d")
            after_timestamp = int(dt.timestamp())
        except ValueError:
            raise ValueError(f"after_date must be YYYY-MM-DD format, got: {after_date}")

    if before_date:
        try:
            dt = datetime.strptime(before_date, "%Y-%m-%d")
            # End of the day
            dt = dt.replace(hour=23, minute=59, second=59)
            before_timestamp = int(dt.timestamp())
        except ValueError:
            raise ValueError(f"before_date must be YYYY-MM-DD format, got: {before_date}")

    def fetch_and_filter_checkins():
        service = SwarmService()
        # Fetch more than requested if filtering, since we'll filter down
        fetch_limit = max_results * 5 if (companion_names or only_with_companions or category_filter) else max_results

        checkins_raw = service.get_self_checkins(
            limit=min(fetch_limit, 250),
            after_timestamp=after_timestamp,
            before_timestamp=before_timestamp,
        )

        entries: list[dict[str, Any]] = []
        for item in checkins_raw:
            # Extract companions from the 'with' field
            companions_raw = item.get("with") or []
            companions = [
                {
                    "id": c.get("id"),
                    "first_name": c.get("firstName"),
                    "last_name": c.get("lastName"),
                    "display_name": c.get("displayName") or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip(),
                }
                for c in companions_raw
            ]

            # Filter by companion names if specified
            if companion_names:
                companion_display_names = [
                    c["display_name"].lower() for c in companions
                ]
                companion_first_names = [
                    (c["first_name"] or "").lower() for c in companions
                ]
                # Check if ALL requested companions are present
                all_found = True
                for name in companion_names:
                    found = any(
                        name in dn or name in fn
                        for dn, fn in zip(companion_display_names, companion_first_names)
                    )
                    if not found:
                        all_found = False
                        break
                if not all_found:
                    continue

            # Filter to only checkins with companions
            if only_with_companions and not companions:
                continue

            # Extract venue info
            info = describe_checkin(item)
            categories = info.get("categories") or []

            # Filter by category
            if category_filter:
                category_match = any(
                    category_filter in cat.lower() for cat in categories
                )
                if not category_match:
                    continue

            entries.append(
                {
                    "iso_time": info.get("iso_time"),
                    "minutes_since": info.get("minutes_since"),
                    "stale": (
                        info.get("minutes_since") is None
                        or info.get("minutes_since") > stale_minutes
                    ),
                    "venue": {
                        "name": info.get("venue_name"),
                        "city": info.get("city"),
                        "state": info.get("state"),
                        "country": info.get("country"),
                        "latitude": info.get("latitude"),
                        "longitude": info.get("longitude"),
                        "canonical_url": info.get("canonical_url"),
                    },
                    "categories": categories,
                    "shout": info.get("shout"),
                    "companions": companions,
                }
            )

            if len(entries) >= max_results:
                break

        return entries

    checkins = await asyncio.to_thread(fetch_and_filter_checkins)

    # Build descriptive message
    filters_desc = []
    if year:
        filters_desc.append(f"in {year}")
    elif after_date or before_date:
        if after_date and before_date:
            filters_desc.append(f"between {after_date} and {before_date}")
        elif after_date:
            filters_desc.append(f"after {after_date}")
        else:
            filters_desc.append(f"before {before_date}")

    if companion_names:
        filters_desc.append(f"with {', '.join(companion_names)}")
    elif only_with_companions:
        filters_desc.append("with companions")

    if category_filter:
        filters_desc.append(f"in '{category_filter}' venues")

    if filters_desc:
        filter_str = " ".join(filters_desc)
        message = f"Found {len(checkins)} check-in(s) {filter_str}."
    else:
        message = (
            f"Showing {len(checkins)} most recent Swarm check-in(s). "
            f"The first entry represents your latest location."
        )

    return {
        "message": message,
        "count": len(checkins),
        "checkins": checkins,
        "filters": {
            "year": year,
            "after_date": after_date,
            "before_date": before_date,
            "with_companion": companion_names or None,
            "only_with_companions": only_with_companions,
            "category": category_filter or None,
        },
    }


SERVER_START_TIME = datetime.now(timezone.utc)


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

    tzinfo = _resolve_timezone(settings.default_timezone)
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
    "list_calendar_events_action",
    "search_contacts_action",
    "create_calendar_event_action",
    "list_calendars_action",
    "list_my_swarm_checkins_action",
    "get_my_time_action",
    "get_server_start_action",
]
