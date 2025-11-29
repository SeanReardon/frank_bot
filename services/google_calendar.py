"""
High-level helper for interacting with the Google Calendar API.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import get_settings

logger = logging.getLogger(__name__)


def _load_credentials(scopes: tuple[str, ...]) -> Credentials:
    """Load OAuth credentials from disk and refresh them if needed."""
    settings = get_settings()
    token_file = settings.google_token_file

    if not os.path.exists(token_file):
        raise FileNotFoundError(
            f"Token file not found: {token_file}. "
            "Run setup_google_credentials.py to generate it."
        )

    creds = Credentials.from_authorized_user_file(token_file, list(scopes))

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Google Calendar credentials")
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Invalid Google Calendar credentials. "
                "Please re-run the OAuth setup."
            )

    return creds


class GoogleCalendarService:
    """Wrapper with convenience methods for reading/writing calendars."""

    def __init__(self, credentials: Credentials | None = None):
        settings = get_settings()
        self._credentials = credentials or _load_credentials(
            settings.google_calendar_scopes
        )
        self._service = build("calendar", "v3", credentials=self._credentials)
        self._calendar_id = "primary"

    def resolve_calendar_id(
        self,
        calendar_id: Optional[str] = None,
        calendar_name: Optional[str] = None,
    ) -> str:
        """Resolve user-provided calendar identifiers to a concrete calendar ID."""
        if calendar_id:
            return calendar_id
        if not calendar_name:
            return self._calendar_id

        page_token = None
        while True:
            response = (
                self._service.calendarList()
                .list(pageToken=page_token, maxResults=250)
                .execute()
            )
            for entry in response.get("items", []):
                summary = entry.get("summary", "")
                if summary.lower() == calendar_name.lower():
                    return entry["id"]
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        raise ValueError(f"Calendar named '{calendar_name}' not found.")

    def list_upcoming_events(
        self,
        *,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return upcoming events ordered by start time."""
        time_min = time_min or f"{datetime.utcnow().isoformat()}Z"
        logger.debug(
            "Fetching upcoming events (max=%s, time_min=%s)",
            max_results,
            time_min,
        )
        params = {
            "calendarId": calendar_id or self._calendar_id,
            "timeMin": time_min,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            params["timeMax"] = time_max
        events_result = (
            self._service.events()
            .list(**params)
            .execute()
        )
        return events_result.get("items", [])

    def create_event(
        self,
        *,
        summary: str,
        description: str | None,
        start_time: datetime,
        end_time: datetime,
        time_zone: str = "UTC",
        extra_fields: Optional[Dict[str, Any]] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event."""
        body: Dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_time.isoformat(), "timeZone": time_zone},
            "end": {"dateTime": end_time.isoformat(), "timeZone": time_zone},
        }
        if description:
            body["description"] = description
        if extra_fields:
            body.update(extra_fields)

        logger.info("Creating Google Calendar event: %s", summary)
        return (
            self._service.events()
            .insert(calendarId=calendar_id or self._calendar_id, body=body)
            .execute()
        )

    def update_event(
        self,
        event_id: str,
        *,
        updates: Dict[str, Any],
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Patch an existing calendar event."""
        logger.info("Updating Google Calendar event %s", event_id)
        return (
            self._service.events()
            .patch(
                calendarId=calendar_id or self._calendar_id,
                eventId=event_id,
                body=updates,
            )
            .execute()
        )

    def delete_event(
        self,
        event_id: str,
        calendar_id: Optional[str] = None,
    ) -> None:
        """Delete an event from the calendar."""
        logger.info("Deleting Google Calendar event %s", event_id)
        try:
            (
                self._service.events()
                .delete(
                    calendarId=calendar_id or self._calendar_id,
                    eventId=event_id,
                )
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                logger.warning("Event %s not found; nothing to delete", event_id)
                return
            raise

    def list_calendars(self) -> List[Dict[str, Any]]:
        """Return metadata for calendars accessible to the user."""
        calendars: List[Dict[str, Any]] = []
        page_token = None
        while True:
            response = (
                self._service.calendarList()
                .list(pageToken=page_token, maxResults=250)
                .execute()
            )
            calendars.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return calendars

