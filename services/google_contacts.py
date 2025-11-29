"""
High-level helper for interacting with the Google Contacts (People) API.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

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
            logger.info("Refreshing expired Google Contacts credentials")
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Invalid Google Contacts credentials. "
                "Please re-run the OAuth setup."
            )

    return creds


class GoogleContactsService:
    """Wrapper with convenience methods for reading/writing contacts."""

    def __init__(self, credentials: Credentials | None = None):
        settings = get_settings()
        self._credentials = credentials or _load_credentials(
            settings.google_contacts_scopes
        )
        self._service = build("people", "v1", credentials=self._credentials)

    def list_contacts(
        self,
        *,
        page_size: int = 100,
        person_fields: Sequence[str] = (
            "names",
            "emailAddresses",
            "phoneNumbers",
        ),
        page_token: str | None = None,
    ) -> Dict[str, Any]:
        """Return contacts plus pagination token."""
        logger.debug("Fetching contacts page (size=%s)", page_size)
        response = (
            self._service.people()
            .connections()
            .list(
                resourceName="people/me",
                pageSize=page_size,
                personFields=",".join(person_fields),
                pageToken=page_token,
            )
            .execute()
        )
        return {
            "connections": response.get("connections", []),
            "nextPageToken": response.get("nextPageToken"),
        }

    def search_contacts(
        self,
        query: str,
        *,
        read_mask: Sequence[str] = (
            "names",
            "emailAddresses",
            "phoneNumbers",
        ),
    ) -> List[Dict[str, Any]]:
        """Search contacts by free-form text."""
        logger.debug("Searching contacts for query=%s", query)
        response = (
            self._service.people()
            .searchContacts(
                query=query,
                readMask=",".join(read_mask),
            )
            .execute()
        )
        return [result.get("person", {}) for result in response.get("results", [])]

    def find_contact_by_email(
        self,
        email: str,
    ) -> dict[str, Any] | None:
        """Return the contact that owns the provided email address, if any."""
        email = (email or "").strip().lower()
        if not email:
            return None
        results = self.search_contacts(email)
        for person in results:
            for entry in person.get("emailAddresses") or []:
                value = (entry.get("value") or "").strip().lower()
                if value == email:
                    return person
        return None

    def contact_exists(self, email: str) -> bool:
        """Boolean helper for verifying a contact contains the email."""
        return self.find_contact_by_email(email) is not None

    def create_contact(
        self,
        *,
        given_name: str,
        family_name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new contact entry."""
        contact: Dict[str, Any] = {
            "names": [
                {
                    "givenName": given_name,
                    "familyName": family_name,
                }
            ]
        }
        if email:
            contact["emailAddresses"] = [{"value": email}]
        if phone:
            contact["phoneNumbers"] = [{"value": phone}]
        if extra_fields:
            contact.update(extra_fields)

        logger.info("Creating Google contact: %s %s", given_name, family_name)
        return self._service.people().createContact(body=contact).execute()

    def update_contact(
        self,
        resource_name: str,
        *,
        contact_body: Dict[str, Any],
        update_person_fields: Sequence[str],
    ) -> Dict[str, Any]:
        """Update an existing contact by resource name."""
        logger.info("Updating Google contact: %s", resource_name)
        return (
            self._service.people()
            .updateContact(
                resourceName=resource_name,
                body=contact_body,
                updatePersonFields=",".join(update_person_fields),
            )
            .execute()
        )

    def delete_contact(self, resource_name: str) -> None:
        """Delete a contact by resource name."""
        logger.info("Deleting Google contact: %s", resource_name)
        try:
            self._service.people().deleteContact(resourceName=resource_name).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                logger.warning("Contact %s not found; nothing to delete", resource_name)
                return
            raise

