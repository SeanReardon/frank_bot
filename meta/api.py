"""
FrankAPI - Synchronous scripting API for Frank Bot.

Provides namespace-based access to Frank Bot actions for use in scripts.
Each namespace wraps the corresponding async action handlers, submitting
coroutines to the main event loop via run_coroutine_threadsafe().

This avoids creating new event loops (which breaks Telethon and other
libraries that bind to a specific loop at connection time).
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

# Reference to the main event loop (set during app startup).
# Scripts run in a ThreadPoolExecutor, so they cannot just asyncio.run()
# because that creates a *new* loop -- which conflicts with services like
# Telethon that bind to the loop they were initialised on.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the main event loop for use by script threads."""
    global _main_loop
    _main_loop = loop


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine from a synchronous (thread-pool) context.

    If the main event loop has been registered (normal server operation),
    the coroutine is submitted to that loop via run_coroutine_threadsafe().
    Otherwise falls back to asyncio.run() for standalone/test usage.
    """
    if _main_loop is not None and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        # 600s matches the default script timeout in meta/executor.py
        return future.result(timeout=600)
    # Fallback for standalone execution (tests, CLI)
    return asyncio.run(coro)


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
        return _run_async(get_events_action(args))

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
        return _run_async(create_event_action(args))

    def update(
        self,
        event_id: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        start: str | None = None,
        end: str | None = None,
        location: str | None = None,
        time_zone: str | None = None,
        calendar_id: str | None = None,
        calendar_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Update a calendar event (Frank_Bot-created events only).

        Frank_Bot can only modify events it created (identified by
        "Created by Frank_Bot" in the description). Attempting to
        update other events returns a helpful error.

        Parameters:
            event_id: Google Calendar event ID (required)
            summary: New event title
            description: New description (tag preserved)
            start: New start time (ISO 8601)
            end: New end time (ISO 8601)
            location: New location
            time_zone: Timezone for start/end
            calendar_id: Specific calendar ID
            calendar_name: Calendar name (fuzzy matched)

        Returns:
            Dict with message, updated event, and calendar info
        """
        from actions.calendar import update_event_action

        args: dict[str, Any] = {"event_id": event_id}
        if summary is not None:
            args["summary"] = summary
        if description is not None:
            args["description"] = description
        if start is not None:
            args["start"] = start
        if end is not None:
            args["end"] = end
        if location is not None:
            args["location"] = location
        if time_zone is not None:
            args["time_zone"] = time_zone
        if calendar_id is not None:
            args["calendar_id"] = calendar_id
        if calendar_name is not None:
            args["calendar_name"] = calendar_name
        return _run_async(update_event_action(args))

    def delete(
        self,
        event_id: str,
        *,
        calendar_id: str | None = None,
        calendar_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Delete a calendar event (Frank_Bot-created events only).

        Frank_Bot can only delete events it created (identified by
        "Created by Frank_Bot" in the description). Attempting to
        delete other events returns a helpful error.

        Parameters:
            event_id: Google Calendar event ID (required)
            calendar_id: Specific calendar ID
            calendar_name: Calendar name (fuzzy matched)

        Returns:
            Dict with message, event_id, and calendar info
        """
        from actions.calendar import delete_event_action

        args: dict[str, Any] = {"event_id": event_id}
        if calendar_id is not None:
            args["calendar_id"] = calendar_id
        if calendar_name is not None:
            args["calendar_name"] = calendar_name
        return _run_async(delete_event_action(args))

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
        return _run_async(get_calendars_action(args))


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
        return _run_async(search_contacts_action(args))


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
        return _run_async(send_sms_action(args))


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
        return _run_async(search_checkins_action(args))


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

        return _run_async(get_ups_status_action())


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
        return _run_async(get_time_action())


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
        return _run_async(send_telegram_message(args))

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
        return _run_async(get_telegram_messages(args))

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
        return _run_async(list_telegram_chats(args))


class TelegramBotNamespace:
    """
    Telegram Bot operations.

    Sends messages using the Bot API (i.e. messages appear from the bot account,
    e.g. `@Seans_frank_bot`). This is distinct from `frank.telegram`, which uses
    Telethon and your personal Telegram account.
    """

    def send(
        self,
        text: str,
        chat_id: str | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a Telegram message via the bot.

        Parameters:
            text: Message content to send
            chat_id: Optional override chat ID (defaults to TELEGRAM_BOT_CHAT_ID)
            parse_mode: Optional Telegram parse mode ("HTML", "MarkdownV2"). If omitted, sends plain text.

        Returns:
            Dict with success status, message_id, and error if any
        """
        from actions.telegram_bot import send_telegram_bot_message

        args = {
            "text": text,
            "chat_id": chat_id,
            "parse_mode": parse_mode,
        }
        return _run_async(send_telegram_bot_message(args))


class AndroidNamespace:
    """
    Android phone operations.

    Wraps Android phone automation actions for LLM-in-the-loop control.
    Provides task-based automation that runs in the background.
    """

    def task_do(
        self,
        goal: str,
        app: str | None = None,
    ) -> dict[str, Any]:
        """
        Start a goal-based task on the Android phone.

        The task runs asynchronously in the background. Use task_get() to
        check progress and get results. The automation stops before any
        irreversible actions like payments or bookings.

        Parameters:
            goal: Natural language description of what to accomplish.
                  Examples:
                  - "Check the thermostat temperature"
                  - "Set the thermostat to 65-70 degrees"
                  - "Open Uber and check ride prices"
            app: Optional app to launch (google_home, uber, lyft, doordash, etc.)
                 Auto-detected from goal if omitted.

        Returns:
            Dict with task_id, status, goal, and message for checking status
        """
        from actions.android_phone import task_do_action

        args = {
            "goal": goal,
            "app": app,
        }
        return _run_async(task_do_action(args))

    def task_get(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        """
        Get the status and result of an Android phone task.

        Parameters:
            task_id: The task ID returned by task_do()

        Returns:
            Dict with task details including status, progress, and results
        """
        from actions.android_phone import task_get_action

        args = {
            "task_id": task_id,
        }
        return _run_async(task_get_action(args))

    def task_cancel(
        self,
        task_id: str,
    ) -> dict[str, Any]:
        """
        Cancel a running Android phone task.

        Parameters:
            task_id: The task ID to cancel

        Returns:
            Dict with task details after cancellation attempt
        """
        from actions.android_phone import task_cancel_action

        args = {
            "task_id": task_id,
        }
        return _run_async(task_cancel_action(args))


class DiagnosticsNamespace:
    """
    Diagnostics operations.

    Wraps diagnostics actions for system health and status checks.
    """

    def full(self) -> dict[str, Any]:
        """
        Get comprehensive diagnostics for all Frank Bot subsystems.

        Returns:
            Dict with server stats, subsystem status, build info, and platform diagnostics
        """
        from actions.diagnostics import get_diagnostics_action

        return _run_async(get_diagnostics_action())

    def health(self) -> dict[str, Any]:
        """
        Quick health check.

        Returns:
            Dict with status, uptime, and build info
        """
        from actions.diagnostics import health_action

        return _run_async(health_action())


class SystemNamespace:
    """
    System operations.

    Wraps system actions for server status, time, and hello world.
    """

    def status(self) -> dict[str, Any]:
        """
        Get orchestration machinery status.

        Returns:
            Dict with switchboard, agent runner, telegram router, message buffer,
            jorbs, and android phone status
        """
        from actions.system_status import get_system_status_action

        return _run_async(get_system_status_action())

    def server(self) -> dict[str, Any]:
        """
        Get server uptime info.

        Returns:
            Dict with message, startup_iso_time, and uptime_seconds
        """
        from actions.system import get_server_status_action

        return _run_async(get_server_status_action())

    def hello(self, name: str = "world") -> dict[str, Any]:
        """
        Hello world action.

        Parameters:
            name: Name to greet (default "world")

        Returns:
            Dict with message and name
        """
        from actions.system import hello_world_action

        args = {"name": name}
        return _run_async(hello_world_action(args))


class JorbsNamespace:
    """
    Jorbs operations.

    Wraps jorb actions for managing long-lived autonomous tasks.
    """

    def list(self, status: str = "open") -> dict[str, Any]:
        """
        List jorbs with optional status filter.

        Parameters:
            status: Filter by "open", "closed", or "all" (default "open")

        Returns:
            Dict with count and jorbs array
        """
        from actions.jorbs import list_jorbs_action

        args = {"status": status}
        return _run_async(list_jorbs_action(args))

    def get(
        self,
        jorb_id: str,
        include_messages: bool = False,
        message_limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get full details for a specific jorb.

        Parameters:
            jorb_id: The jorb ID
            include_messages: Include message history
            message_limit: Max messages to include (default 50)

        Returns:
            Dict with full jorb details and optionally messages
        """
        from actions.jorbs import get_jorb_action

        args = {
            "jorb_id": jorb_id,
            "include_messages": include_messages,
            "message_limit": message_limit,
        }
        return _run_async(get_jorb_action(args))

    def create(
        self,
        name: str,
        plan: str,
        contacts: list | None = None,
        personality: str = "default",
        start_immediately: bool = True,
    ) -> dict[str, Any]:
        """
        Create a new jorb (long-lived autonomous task).

        Parameters:
            name: Human-readable task name
            plan: Full plan text describing what to do
            contacts: Array of contact dicts [{identifier, channel, name?}]
            personality: LLM personality (default, concierge, researcher, etc.)
            start_immediately: Begin right away (default True)

        Returns:
            Dict with created jorb details
        """
        from actions.jorbs import create_jorb_action

        args = {
            "name": name,
            "plan": plan,
            "contacts": contacts,
            "personality": personality,
            "start_immediately": start_immediately,
        }
        return _run_async(create_jorb_action(args))

    def approve(self, jorb_id: str, decision: str) -> dict[str, Any]:
        """
        Approve a paused or planning jorb.

        Parameters:
            jorb_id: The jorb ID
            decision: The approval decision/instructions

        Returns:
            Dict with updated jorb status
        """
        from actions.jorbs import approve_jorb_action

        args = {"jorb_id": jorb_id, "decision": decision}
        return _run_async(approve_jorb_action(args))

    def cancel(self, jorb_id: str, reason: str = "") -> dict[str, Any]:
        """
        Cancel a jorb.

        Parameters:
            jorb_id: The jorb ID
            reason: Reason for cancellation

        Returns:
            Dict with updated jorb status
        """
        from actions.jorbs import cancel_jorb_action

        args = {"jorb_id": jorb_id, "reason": reason}
        return _run_async(cancel_jorb_action(args))

    def stats(self, status: str = "all") -> dict[str, Any]:
        """
        Get aggregate statistics for jorbs.

        Parameters:
            status: Filter by "open", "closed", or "all" (default "all")

        Returns:
            Dict with aggregate metrics and status counts
        """
        from actions.jorbs import get_jorbs_stats_action

        args = {"status": status}
        return _run_async(get_jorbs_stats_action(args))

    def brief(self, hours: int = 24) -> dict[str, Any]:
        """
        Get an activity summary since the last briefing.

        Parameters:
            hours: Only show activity from last N hours (default 24)

        Returns:
            Dict with needs_attention, activity_summary, highlights, pending_decisions
        """
        from actions.jorbs import brief_me_action

        args = {"hours": hours}
        return _run_async(brief_me_action(args))

    def messages(
        self,
        jorb_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Get message history for a jorb.

        Parameters:
            jorb_id: The jorb ID
            limit: Max messages (default 50)
            offset: Skip first N messages (default 0)

        Returns:
            Dict with messages array
        """
        from actions.jorbs import get_jorb_messages_action

        args = {
            "jorb_id": jorb_id,
            "limit": limit,
            "offset": offset,
        }
        return _run_async(get_jorb_messages_action(args))


class ClaudiaNamespace:
    """
    Claudia operations.

    Wraps Claudia actions for AI coding assistant conversations and prompt execution.
    """

    def repos(self) -> dict[str, Any]:
        """
        List all Claudia-managed repositories.

        Returns:
            Dict with count and repos list
        """
        from actions.claudia import list_claudia_repos_action

        return _run_async(list_claudia_repos_action())

    def chat_create(
        self,
        repo_name: str,
        title: str,
        message: str | None = None,
    ) -> dict[str, Any]:
        """
        Start a conversation with Claudia about a repository.

        Parameters:
            repo_name: Name of the repository
            title: Chat title/topic
            message: Initial message (optional)

        Returns:
            Dict with chat session info
        """
        from actions.claudia import create_claudia_chat_action

        args = {
            "repo_name": repo_name,
            "title": title,
            "message": message,
        }
        return _run_async(create_claudia_chat_action(args))

    def chat_list(
        self,
        repo_id: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        List chats for a repository.

        Parameters:
            repo_id: Repository ID
            status: Filter by status: active, completed, cancelled (optional)

        Returns:
            Dict with count and chats list
        """
        from actions.claudia import list_claudia_chats_action

        args: dict[str, Any] = {"repo_id": repo_id}
        if status is not None:
            args["status"] = status
        return _run_async(list_claudia_chats_action(args))

    def chat_get(self, repo_id: str, chat_id: str) -> dict[str, Any]:
        """
        Get the current state of a chat.

        Parameters:
            repo_id: Repository ID
            chat_id: Chat ID

        Returns:
            Dict with chat session and messages
        """
        from actions.claudia import get_claudia_chat_action

        args = {"repo_id": repo_id, "chat_id": chat_id}
        return _run_async(get_claudia_chat_action(args))

    def chat_send(
        self,
        repo_id: str,
        chat_id: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Send a message in an active chat.

        Parameters:
            repo_id: Repository ID
            chat_id: Chat ID
            message: Message content

        Returns:
            Dict with created message
        """
        from actions.claudia import send_claudia_message_action

        args = {
            "repo_id": repo_id,
            "chat_id": chat_id,
            "message": message,
        }
        return _run_async(send_claudia_message_action(args))

    def chat_end(self, repo_id: str, chat_id: str) -> dict[str, Any]:
        """
        End a chat session.

        Parameters:
            repo_id: Repository ID
            chat_id: Chat ID

        Returns:
            Dict with final chat state
        """
        from actions.claudia import end_claudia_chat_action

        args = {"repo_id": repo_id, "chat_id": chat_id}
        return _run_async(end_claudia_chat_action(args))

    def prompts(self, repo_id: str) -> dict[str, Any]:
        """
        List all prompts for a repository.

        Parameters:
            repo_id: Repository ID

        Returns:
            Dict with prompts list
        """
        from actions.claudia import list_claudia_prompts_action

        args = {"repo_id": repo_id}
        return _run_async(list_claudia_prompts_action(args))

    def prompt_get(self, repo_id: str, prompt_id: str) -> dict[str, Any]:
        """
        Get details of a specific prompt.

        Parameters:
            repo_id: Repository ID
            prompt_id: Prompt ID

        Returns:
            Dict with prompt details
        """
        from actions.claudia import get_claudia_prompt_action

        args = {"repo_id": repo_id, "prompt_id": prompt_id}
        return _run_async(get_claudia_prompt_action(args))

    def prompt_execute(self, repo_id: str, prompt_id: str) -> dict[str, Any]:
        """
        Execute a prompt directly.

        Parameters:
            repo_id: Repository ID
            prompt_id: Prompt ID

        Returns:
            Dict with queue item info
        """
        from actions.claudia import execute_claudia_prompt_action

        args = {"repo_id": repo_id, "prompt_id": prompt_id}
        return _run_async(execute_claudia_prompt_action(args))

    def queue(self, repo_id: str) -> dict[str, Any]:
        """
        Get the queue status for a repository.

        Parameters:
            repo_id: Repository ID

        Returns:
            Dict with queue status
        """
        from actions.claudia import get_claudia_queue_action

        args = {"repo_id": repo_id}
        return _run_async(get_claudia_queue_action(args))

    def executions(
        self,
        repo_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List executions with optional filters.

        Parameters:
            repo_id: Filter by repository (optional)
            status: Filter by status (optional)
            limit: Max results (default 50)

        Returns:
            Dict with executions list
        """
        from actions.claudia import list_claudia_executions_action

        args = {
            "repo_id": repo_id,
            "status": status,
            "limit": limit,
        }
        return _run_async(list_claudia_executions_action(args))

    def execution_get(self, execution_id: str) -> dict[str, Any]:
        """
        Get execution details.

        Parameters:
            execution_id: Execution ID

        Returns:
            Dict with execution details
        """
        from actions.claudia import get_claudia_execution_action

        args = {"execution_id": execution_id}
        return _run_async(get_claudia_execution_action(args))


class StyleNamespace:
    """
    Style operations.

    Wraps style capture actions for generating SEAN.md style guide.
    """

    def generate(
        self,
        chat_id: str | None = None,
        dry_run: bool = False,
        before_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate SEAN.md from message analysis.

        Parameters:
            chat_id: Chat to fetch messages from (default: @MagicConciergeBot)
            dry_run: If true, generate but don't send (default False)
            before_date: Only analyze messages before this date (ISO 8601)

        Returns:
            Dict with success status, message count, and content preview
        """
        from actions.style_capture import generate_sean_md_action

        args = {
            "chat_id": chat_id,
            "dry_run": dry_run,
            "before_date": before_date,
        }
        return _run_async(generate_sean_md_action(args))


class EarshotNamespace:
    """
    Earshot transcript operations.

    Search, query, and analyze audio transcripts captured by the Earshot system.
    Uses LLM-powered queries to extract insights across transcript history.
    """

    def _client(self):
        from services.earshot_client import EarshotClient
        return EarshotClient()

    def search(
        self,
        *,
        q: str | None = None,
        source: str | None = None,
        location: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """
        Search transcripts with optional filters.

        Parameters:
            q: Full-text search query
            source: Filter by source (e.g. "plaud")
            location: Filter by location
            since: Only transcripts after this date (YYYY-MM-DD or ISO 8601)
            until: Only transcripts before this date (YYYY-MM-DD or ISO 8601)
            limit: Max results (1-200, default 20)
            offset: Skip first N results (default 0)

        Returns:
            List of transcript dicts with id, title, started_at, summary, etc.
        """
        return self._client().list_transcripts(
            q=q, source=source, location=location,
            since=since, until=until, limit=limit, offset=offset,
        )

    def get(self, transcript_id: int) -> dict:
        """
        Get a single transcript by ID.

        Parameters:
            transcript_id: The transcript ID

        Returns:
            Transcript dict with full content
        """
        return self._client().get_transcript(transcript_id)

    def query(
        self,
        *,
        earliest: str,
        latest: str,
        prompt: str,
        terms: list[str] | None = None,
    ) -> dict:
        """
        Run an LLM query across transcripts in a date range and return all results.

        Creates the query, then blocks until results are ready. For large date
        ranges this may take 30-60 seconds.

        Parameters:
            earliest: Start date (YYYY-MM-DD)
            latest: End date (YYYY-MM-DD)
            prompt: What to look for / extract (natural language)
            terms: Optional keyword filter (AND-matched before LLM processing)

        Returns:
            Dict with queryId, status, results list, totalResults, totalMatched
        """
        client = self._client()
        created = client.query_create(
            earliest=earliest, latest=latest, prompt=prompt, terms=terms,
        )
        query_id = created["queryId"]
        return client.query_results(query_id)

    def query_start(
        self,
        *,
        earliest: str,
        latest: str,
        prompt: str,
        terms: list[str] | None = None,
    ) -> dict:
        """
        Start an async LLM query (non-blocking). Returns a query_id for polling.

        Use query_results(), query_first(), or query_next() to retrieve results.

        Parameters:
            earliest: Start date (YYYY-MM-DD)
            latest: End date (YYYY-MM-DD)
            prompt: What to look for / extract (natural language)
            terms: Optional keyword filter

        Returns:
            Dict with queryId and status ("processing")
        """
        return self._client().query_create(
            earliest=earliest, latest=latest, prompt=prompt, terms=terms,
        )

    def query_results(self, query_id: str, *, raw: bool = False) -> dict:
        """
        Get all results for a query (blocks until complete).

        Parameters:
            query_id: The query ID from query_start()
            raw: Include full transcript text in each result

        Returns:
            Dict with queryId, status, results list, totalResults, totalMatched
        """
        return self._client().query_results(query_id, raw=raw)

    def query_first(self, query_id: str, *, raw: bool = False) -> dict:
        """
        Get the first result and reset the cursor.

        Parameters:
            query_id: The query ID from query_start()
            raw: Include full transcript text

        Returns:
            Dict with queryId, status, result, totalResults, index
        """
        return self._client().query_first(query_id, raw=raw)

    def query_next(self, query_id: str, *, raw: bool = False) -> dict:
        """
        Advance cursor and get the next result.

        Parameters:
            query_id: The query ID from query_start()
            raw: Include full transcript text

        Returns:
            Dict with queryId, status, result, totalResults, index, done
        """
        return self._client().query_next(query_id, raw=raw)

    def transform(self, transcript_file: str, prompt: str) -> dict:
        """
        Transform a single transcript via LLM.

        Parameters:
            transcript_file: Filename of the transcript JSON file
            prompt: What to extract or how to transform

        Returns:
            Dict with transcriptFile, result, usage
        """
        return self._client().transform(transcript_file, prompt)

    def count(self, earliest: str, latest: str) -> dict:
        """
        Count transcripts in a date range.

        Parameters:
            earliest: Start date (YYYY-MM-DD)
            latest: End date (YYYY-MM-DD)

        Returns:
            Dict with count, earliest, latest
        """
        return self._client().count(earliest, latest)

    def date_parse(self, text: str) -> dict:
        """
        Parse natural language date text into a date range.

        Parameters:
            text: Natural language like "last week", "January 2026", "yesterday"

        Returns:
            Dict with earliest (YYYY-MM-DD), latest (YYYY-MM-DD), confidence
        """
        return self._client().date_parse(text)

    def worker_trigger(self, force: bool = False) -> dict:
        """
        Trigger a worker run to evaluate standard queries on new transcripts.

        Parameters:
            force: Re-evaluate all transcripts, not just new ones

        Returns:
            Dict with status and message
        """
        return self._client().worker_trigger(force=force)

    def worker_status(self) -> dict:
        """
        Get the latest worker run status.

        Returns:
            Dict with worker run stats or {status: "no_runs"}
        """
        return self._client().worker_status()

    def dashboard(self, page: int = 1, limit: int = 50) -> dict:
        """
        Get the dashboard grid (transcripts merged with standard query results).

        Parameters:
            page: Page number (1-based, default 1)
            limit: Results per page (1-200, default 50)

        Returns:
            Dict with columns, rows, page, limit, totalPages, totalTranscripts
        """
        return self._client().dashboard_grid(page=page, limit=limit)

    def diagnostics(self) -> dict:
        """
        Get earshot system diagnostics (transcript count, git commit).

        Returns:
            Dict with transcript_count and git_commit
        """
        return self._client().diagnostics()


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
        self._telegram_bot = TelegramBotNamespace()
        self._android = AndroidNamespace()
        self._diagnostics = DiagnosticsNamespace()
        self._system = SystemNamespace()
        self._jorbs = JorbsNamespace()
        self._claudia = ClaudiaNamespace()
        self._earshot = EarshotNamespace()
        self._style = StyleNamespace()

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

    @property
    def telegram_bot(self) -> TelegramBotNamespace:
        """Telegram Bot operations (send)."""
        return self._telegram_bot

    @property
    def android(self) -> AndroidNamespace:
        """Android phone operations (task_do, task_get, task_cancel)."""
        return self._android

    @property
    def diagnostics(self) -> DiagnosticsNamespace:
        """Diagnostics operations (full, health)."""
        return self._diagnostics

    @property
    def system(self) -> SystemNamespace:
        """System operations (status, server, hello)."""
        return self._system

    @property
    def jorbs(self) -> JorbsNamespace:
        """Jorbs operations (list, get, create, approve, cancel, stats, brief, messages)."""
        return self._jorbs

    @property
    def claudia(self) -> ClaudiaNamespace:
        """Claudia operations (repos, chat_create, chat_list, chat_get, chat_send, chat_end, prompts, prompt_get, prompt_execute, queue, executions, execution_get)."""
        return self._claudia

    @property
    def earshot(self) -> EarshotNamespace:
        """Earshot transcript operations (search, query, transform, count, date_parse, dashboard)."""
        return self._earshot

    @property
    def style(self) -> StyleNamespace:
        """Style operations (generate)."""
        return self._style


__all__ = [
    "FrankAPI",
    "CalendarNamespace",
    "ContactsNamespace",
    "SMSNamespace",
    "SwarmNamespace",
    "UPSNamespace",
    "TimeNamespace",
    "TelegramNamespace",
    "TelegramBotNamespace",
    "AndroidNamespace",
    "DiagnosticsNamespace",
    "SystemNamespace",
    "JorbsNamespace",
    "ClaudiaNamespace",
    "EarshotNamespace",
    "StyleNamespace",
    "set_main_loop",
]
