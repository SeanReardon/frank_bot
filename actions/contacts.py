"""
Google Contacts actions: search contacts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from actions.helpers import coerce_int
from services.google_contacts import GoogleContactsService

logger = logging.getLogger(__name__)


async def search_contacts_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = arguments or {}
    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required to search contacts.")

    max_results = coerce_int(
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


__all__ = ["search_contacts_action"]
