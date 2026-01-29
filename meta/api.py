"""
FrankAPI - Synchronous scripting API for Frank Bot.

Provides namespace-based access to Frank Bot actions for use in scripts.
Each namespace wraps the corresponding async action handlers with
synchronous methods using asyncio.run().
"""

from __future__ import annotations

import asyncio
from typing import Any


class CalendarNamespace:
    """
    Calendar operations.

    Wraps Google Calendar actions for event management.
    """

    def events(
        self,
        *,
        day: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        time_zone: str | None = None,
        calendar_id: str | None = None,
        calendar_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Get calendar events.

        Parameters:
            day: Date to get events for (YYYY-MM-DD format)
            time_min: Start of time range (ISO 8601)
            time_max: End of time range (ISO 8601)
            max_results: Maximum number of events to return (1-50)
            time_zone: Timezone for display (e.g., "America/Chicago")
            calendar_id: Specific calendar ID to query
            calendar_name: Calendar name to query (fuzzy matched)

        Returns:
            Dict with message, calendar info, time_window, count, and events list
        """
        from actions.calendar import get_events_action

        args = {
            "day": day,
            "time_min": time_min,
            "time_max": time_max,
            "max_results": max_results,
            "time_zone": time_zone,
            "calendar_id": calendar_id,
            "calendar_name": calendar_name,
        }
        return asyncio.run(get_events_action(args))

    def create(
        self,
        *,
        summary: str,
        start: str,
        end: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        time_zone: str | None = None,
        calendar_id: str | None = None,
        calendar_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a calendar event.

        Parameters:
            summary: Event title
            start: Start time (ISO 8601)
            end: End time (ISO 8601)
            description: Event description
            location: Event location (e.g., "Nerdvana, Frisco, TX")
            attendees: List of attendee email addresses
            time_zone: Timezone for the event
            calendar_id: Calendar ID to create event on
            calendar_name: Calendar name to create event on (fuzzy matched)

        Returns:
            Dict with message, event details, and calendar info
        """
        from actions.calendar import create_event_action

        args = {
            "summary": summary,
            "start": start,
            "end": end,
            "description": description,
            "location": location,
            "attendees": attendees,
            "time_zone": time_zone,
            "calendar_id": calendar_id,
            "calendar_name": calendar_name,
        }
        return asyncio.run(create_event_action(args))

    def list(
        self,
        *,
        include_access_role: bool = False,
        primary_only: bool = False,
    ) -> dict[str, Any]:
        """
        List available calendars.

        Parameters:
            include_access_role: Include access role in response
            primary_only: Only return primary calendar

        Returns:
            Dict with message, count, and calendars list
        """
        from actions.calendar import get_calendars_action

        args = {
            "include_access_role": include_access_role,
            "primary_only": primary_only,
        }
        return asyncio.run(get_calendars_action(args))


class ContactsNamespace:
    """
    Contact operations.

    Wraps Google Contacts actions for contact lookup.
    """

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> dict[str, Any]:
        """
        Search contacts.

        Parameters:
            query: Search query (name, email, phone)
            max_results: Maximum number of results (1-50)

        Returns:
            Dict with message, query, count, and contacts list
        """
        from actions.contacts import search_contacts_action

        args = {
            "query": query,
            "max_results": max_results,
        }
        return asyncio.run(search_contacts_action(args))


class SMSNamespace:
    """
    SMS operations.

    Wraps Telnyx SMS actions for sending text messages.
    """

    def send(
        self,
        recipient: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Send an SMS message.

        Parameters:
            recipient: Contact name or phone number
            message: Message text to send

        Returns:
            Dict with message, success status, recipient info, and message details
        """
        from actions.sms import send_sms_action

        args = {
            "recipient": recipient,
            "message": message,
        }
        return asyncio.run(send_sms_action(args))


class SwarmNamespace:
    """
    Swarm/Foursquare operations.

    Wraps Swarm actions for checkin history and location data.
    """

    def checkins(
        self,
        *,
        year: int | str | None = None,
        after_date: str | None = None,
        before_date: str | None = None,
        category: str | None = None,
        with_companion: str | list[str] | None = None,
        companion_match: str = "any",
        only_with_companions: bool = False,
        has_photos: bool = False,
        include_photos: bool = False,
        max_results: int = 10,
        stale_minutes: int = 180,
    ) -> dict[str, Any]:
        """
        Search Swarm checkins.

        Parameters:
            year: Filter by year (e.g., 2024)
            after_date: Filter checkins after this date (YYYY-MM-DD)
            before_date: Filter checkins before this date (YYYY-MM-DD)
            category: Filter by venue category (e.g., "restaurant", "hotel")
            with_companion: Filter by companion name(s)
            companion_match: "any" (OR) or "all" (AND) for multiple companions
            only_with_companions: Only include checkins with companions
            has_photos: Only include checkins with photos
            include_photos: Include photo URLs in response
            max_results: Maximum number of results (1-250)
            stale_minutes: Minutes after which a checkin is considered stale

        Returns:
            Dict with message, count, checkins list, and applied filters
        """
        from actions.swarm import search_checkins_action

        args = {
            "year": year,
            "after_date": after_date,
            "before_date": before_date,
            "category": category,
            "with_companion": with_companion,
            "companion_match": companion_match,
            "only_with_companions": only_with_companions,
            "has_photos": has_photos,
            "include_photos": include_photos,
            "max_results": max_results,
            "stale_minutes": stale_minutes,
        }
        return asyncio.run(search_checkins_action(args))


class UPSNamespace:
    """
    UPS status operations.

    Wraps UPS monitoring actions for power status.
    """

    def status(self) -> dict[str, Any]:
        """
        Get UPS status.

        Returns:
            Dict with message, runtime info, charge percent, and temperature
        """
        from actions.ups import get_ups_status_action

        return asyncio.run(get_ups_status_action())


class TimeNamespace:
    """
    Time operations.

    Wraps time actions for current time with timezone awareness.
    """

    def now(
        self,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """
        Get current time.

        The time is derived from your latest Swarm checkin if available,
        otherwise falls back to the configured default timezone.

        Parameters:
            timezone: Optional timezone override (not currently used by underlying action)

        Returns:
            Dict with message, iso_time, timezone, and offset_minutes
        """
        from actions.system import get_time_action

        # Note: get_time_action doesn't currently support timezone parameter
        # but the namespace signature includes it for future compatibility
        return asyncio.run(get_time_action())


class TelegramNamespace:
    """
    Telegram operations.

    Wraps Telegram actions for messaging via your personal Telegram account (not a bot).
    Requires prior authentication via the setup script.
    """

    def send(
        self,
        recipient: str,
        text: str,
    ) -> dict[str, Any]:
        """
        Send a Telegram message.

        Parameters:
            recipient: Username (with or without @), phone number, or chat ID
            text: Message text to send

        Returns:
            Dict with success status, recipient info, and message details
        """
        from actions.telegram import send_telegram_message

        args = {
            "recipient": recipient,
            "text": text,
        }
        return asyncio.run(send_telegram_message(args))

    def messages(
        self,
        chat: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Get messages from a Telegram chat.

        Parameters:
            chat: Username, phone number, or chat ID
            limit: Maximum number of messages to retrieve (1-100, default 20)

        Returns:
            Dict with list of messages and metadata
        """
        from actions.telegram import get_telegram_messages

        args = {
            "chat": chat,
            "limit": limit,
        }
        return asyncio.run(get_telegram_messages(args))

    def chats(
        self,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List recent Telegram conversations.

        Parameters:
            limit: Maximum number of chats to retrieve (1-100, default 20)

        Returns:
            Dict with list of chats and metadata
        """
        from actions.telegram import list_telegram_chats

        args = {
            "limit": limit,
        }
        return asyncio.run(list_telegram_chats(args))


class FrankAPI:
    """
    Synchronous API for Frank Bot scripting.

    Provides namespace-based access to all Frank Bot actions.
    Each namespace contains synchronous wrapper methods that call
    the underlying async action handlers.

    Example:
        frank = FrankAPI()
        events = frank.calendar.events(day="2024-01-15")
        contacts = frank.contacts.search("John")
        checkins = frank.swarm.checkins(year=2024, category="restaurant")
    """

    def __init__(self) -> None:
        self._calendar = CalendarNamespace()
        self._contacts = ContactsNamespace()
        self._sms = SMSNamespace()
        self._swarm = SwarmNamespace()
        self._ups = UPSNamespace()
        self._time = TimeNamespace()
        self._telegram = TelegramNamespace()

    @property
    def calendar(self) -> CalendarNamespace:
        """Calendar operations (events, create, list)."""
        return self._calendar

    @property
    def contacts(self) -> ContactsNamespace:
        """Contact operations (search)."""
        return self._contacts

    @property
    def sms(self) -> SMSNamespace:
        """SMS operations (send)."""
        return self._sms

    @property
    def swarm(self) -> SwarmNamespace:
        """Swarm/Foursquare operations (checkins)."""
        return self._swarm

    @property
    def ups(self) -> UPSNamespace:
        """UPS status operations (status)."""
        return self._ups

    @property
    def time(self) -> TimeNamespace:
        """Time operations (now)."""
        return self._time

    @property
    def telegram(self) -> TelegramNamespace:
        """Telegram operations (send, messages, chats)."""
        return self._telegram


__all__ = [
    "FrankAPI",
    "CalendarNamespace",
    "ContactsNamespace",
    "SMSNamespace",
    "SwarmNamespace",
    "UPSNamespace",
    "TimeNamespace",
    "TelegramNamespace",
]
