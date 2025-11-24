"""
Factory helpers to initialize the MCP server instance.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any, Awaitable, Callable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server import Server
from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

from frank_bot.config import get_settings
from frank_bot.services.google_calendar import GoogleCalendarService
from frank_bot.services.google_contacts import GoogleContactsService

logger = logging.getLogger(__name__)

ToolResponse = Sequence[TextContent | ImageContent | EmbeddedResource]
ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResponse]]


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
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _parse_iso_datetime(value: str) -> datetime:
    """Parse ISO8601 datetimes while allowing trailing Z."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:  # pragma: no cover
        raise ValueError(f"Invalid ISO8601 datetime: {value}") from exc


def create_mcp_server(name: str = "frank-bot") -> Server:
    """Instantiate the MCP server and register builtin tools."""
    server = Server(name)
    settings = get_settings()
    logger.info("MCP server '%s' initialized", name)

    tools: list[Tool] = []
    handlers: dict[str, ToolHandler] = {}

    def register_tool(tool: Tool, handler: ToolHandler) -> None:
        tools.append(tool)
        handlers[tool.name] = handler
        logger.info(
            "Registered tool '%s' (%s). Total tools: %s",
            tool.name,
            tool.description,
            len(tools),
        )

    async def hello_world_handler(arguments: dict[str, Any]) -> ToolResponse:
        name = arguments.get("name") if arguments else None
        message = f"hello {name or 'world'}"
        return [TextContent(type="text", text=message)]

    register_tool(
        Tool(
            name="hello_world",
            description="A simple hello world tool that greets the user",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Optional name to include in the greeting."
                        ),
                    }
                },
            },
        ),
        hello_world_handler,
    )

    async def list_calendar_events_handler(
        arguments: dict[str, Any],
    ) -> ToolResponse:
        args = arguments or {}
        max_results = int(args.get("max_results", 10))
        max_results = max(1, min(max_results, 50))

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
            start_dt = datetime.combine(
                target_day,
                dt_time.min,
                tzinfo=tzinfo,
            )
            end_dt = start_dt + timedelta(days=1)
            time_min = start_dt.isoformat()
            time_max = end_dt.isoformat()
        elif not time_min and not time_max:
            today = datetime.now(tzinfo).date()
            start_dt = datetime.combine(
                today,
                dt_time.min,
                tzinfo=tzinfo,
            )
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
            summary_range = (
                f"{time_min or 'now'} to {time_max or 'open-ended'}"
            )
            message = (
                f"No calendar events scheduled between {summary_range} "
                f"on calendar '{calendar_label}'."
            )
        else:
            lines = [
                f"Found {len(events)} event(s) on '{calendar_label}':",
            ]
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

        return [TextContent(type="text", text=message)]

    register_tool(
        Tool(
            name="list_calendar_events",
            description=(
                "Retrieve Google Calendar events for a specific day or "
                "time range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": (
                            "ISO date (YYYY-MM-DD). When provided, events "
                            "for that day in the specified timezone are "
                            "returned."
                        ),
                    },
                    "time_min": {
                        "type": "string",
                        "description": (
                            "RFC3339/ISO timestamp for the beginning of the "
                            "search window. Overrides 'day' if supplied."
                        ),
                    },
                    "time_max": {
                        "type": "string",
                        "description": (
                            "RFC3339/ISO timestamp for the end of the window."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return.",
                    },
                    "time_zone": {
                        "type": "string",
                        "description": (
                            "IANA timezone name used when computing day-based "
                            "ranges. Defaults to DEFAULT_TIMEZONE env."
                        ),
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": (
                            "Optional calendar ID to query. Defaults to the "
                            "primary calendar."
                        ),
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": (
                            "Optional calendar display name; used when a user "
                            "has access to multiple calendars."
                        ),
                    },
                }
            },
        ),
        list_calendar_events_handler,
    )

    async def search_contacts_handler(
        arguments: dict[str, Any]
    ) -> ToolResponse:
        args = arguments or {}
        query = (args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required to search contacts.")

        max_results = int(args.get("max_results", 10))
        max_results = max(1, min(max_results, 50))

        def fetch_contacts():
            service = GoogleContactsService()
            results = service.search_contacts(query=query)
            return results[:max_results]

        contacts = await asyncio.to_thread(fetch_contacts)
        if not contacts:
            message = f"No contacts matched '{query}'."
        else:
            lines = [f"Top {len(contacts)} contact match(es) for '{query}':"]
            for person in contacts:
                names = person.get("names", [])
                display_name = (
                    names[0].get("displayName")
                    if names
                    else "Unnamed contact"
                )
                line = f"- {display_name}"

                emails = person.get("emailAddresses", [])
                email_values = [
                    email.get("value")
                    for email in emails
                    if email.get("value")
                ]
                phones = person.get("phoneNumbers", [])
                phone_values = [
                    phone.get("value")
                    for phone in phones
                    if phone.get("value")
                ]

                details = []
                if email_values:
                    details.append("Emails: " + ", ".join(email_values))
                if phone_values:
                    details.append("Phones: " + ", ".join(phone_values))
                if details:
                    line += f" ({'; '.join(details)})"

                lines.append(line)

            message = "\n".join(lines)

        return [TextContent(type="text", text=message)]

    register_tool(
        Tool(
            name="search_contacts",
            description=(
                "Search Google Contacts (People API) by name, email, or phone."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-form text that can include names, "
                            "emails, or phone numbers."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of contacts to return.",
                    },
                },
                "required": ["query"],
            },
        ),
        search_contacts_handler,
    )

    async def create_calendar_event_handler(
        arguments: dict[str, Any],
    ) -> ToolResponse:
        args = arguments or {}
        try:
            summary = args["summary"]
            start_raw = args["start"]
            end_raw = args["end"]
        except KeyError as exc:
            raise ValueError(
                "summary, start, and end are required to create an event."
            ) from exc

        attendees = args.get("attendees") or []
        description = args.get("description")
        time_zone = args.get("time_zone") or settings.default_timezone
        calendar_id_arg = args.get("calendar_id")
        calendar_name = args.get("calendar_name")
        resolved_calendar_id: str | None = None

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
            if attendees:
                extra_fields["attendees"] = [
                    {"email": email} for email in attendees if email
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
        text = (
            f"Created event '{created_event.get('summary', summary)}' "
            f"from {start_desc} to {end_desc} "
            f"on calendar '{calendar_label}'"
        )
        return [TextContent(type="text", text=text)]

    register_tool(
        Tool(
            name="create_calendar_event",
            description=(
                "Create a Google Calendar event with optional attendees."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start": {
                        "type": "string",
                        "description": "Start time in ISO 8601 format.",
                    },
                    "end": {
                        "type": "string",
                        "description": "End time in ISO 8601 format.",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Email addresses for attendees.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description.",
                    },
                    "time_zone": {
                        "type": "string",
                        "description": (
                            "Optional IANA timezone name. Defaults to "
                            "DEFAULT_TIMEZONE."
                        ),
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": (
                            "Optional calendar ID to create the event in."
                        ),
                    },
                    "calendar_name": {
                        "type": "string",
                        "description": (
                            "Optional calendar name if you prefer to select "
                            "by display name."
                        ),
                    },
                },
                "required": ["summary", "start", "end"],
            },
        ),
        create_calendar_event_handler,
    )

    async def list_calendars_handler(
        arguments: dict[str, Any]
    ) -> ToolResponse:
        args = arguments or {}
        include_access_role = bool(args.get("include_access_role", False))
        include_primary_only = bool(args.get("primary_only", False))

        def fetch_calendars():
            service = GoogleCalendarService()
            calendars = service.list_calendars()
            if include_primary_only:
                calendars = [
                    cal for cal in calendars if cal.get("primary") is True
                ]
            results = []
            for cal in calendars:
                entry = {
                    "id": cal.get("id"),
                    "summary": cal.get("summary"),
                    "timeZone": cal.get("timeZone"),
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

        return [TextContent(type="text", text=text)]

    register_tool(
        Tool(
            name="list_calendars",
            description="List calendars accessible to the authenticated user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_access_role": {
                        "type": "boolean",
                        "description": (
                            "Include the accessRole for each calendar. "
                            "Defaults to false."
                        ),
                    },
                    "primary_only": {
                        "type": "boolean",
                        "description": (
                            "Return only the primary calendar if true."
                        ),
                    },
                },
            },
        ),
        list_calendars_handler,
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        logger.info("=== ChatGPT Request: list_tools() ===")
        response_data = {
            "request_type": "list_tools",
            "tools_count": len(tools),
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in tools
            ],
        }
        logger.info(
            "=== ChatGPT Request (JSON) ===\n%s",
            json.dumps(response_data, indent=2),
        )
        return tools

    @server.call_tool()
    async def call_tool(
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> ToolResponse:
        request_data = {
            "request_type": "call_tool",
            "tool_name": tool_name,
            "arguments": arguments or {},
        }
        logger.info("=== ChatGPT Request: call_tool() ===")
        logger.info(
            "=== ChatGPT Request (JSON) ===\n%s",
            json.dumps(request_data, indent=2),
        )

        handler = handlers.get(tool_name)
        if not handler:
            error_data = {
                "request_type": "call_tool",
                "tool_name": tool_name,
                "error": f"Unknown tool: {tool_name}",
            }
            logger.error(
                "=== Error Response (JSON) ===\n%s",
                json.dumps(error_data, indent=2),
            )
            raise ValueError(f"Unknown tool: {tool_name}")

        result = await handler(arguments or {})
        response_data = {
            "request_type": "call_tool",
            "tool_name": tool_name,
            "response_count": len(result),
        }
        logger.info(
            "=== Response to ChatGPT (JSON) ===\n%s",
            json.dumps(response_data, indent=2, default=str),
        )
        return result

    return server
