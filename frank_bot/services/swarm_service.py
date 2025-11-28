"""
Helpers for interacting with the Swarm/Foursquare API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from frank_bot.config import get_settings

logger = logging.getLogger(__name__)


class SwarmAPIError(RuntimeError):
    """Raised when the Swarm API returns an error response."""


@dataclass(frozen=True)
class SwarmUser:
    id: str
    display_name: str


class SwarmService:
    """Thin wrapper around the Foursquare/Swarm REST API."""

    API_BASE = "https://api.foursquare.com/v2"

    def __init__(self) -> None:
        settings = get_settings()
        token = settings.swarm_oauth_token
        if not token:
            raise ValueError(
                "SWARM_OAUTH_TOKEN is not configured. "
                "Set it in your environment to enable Swarm tools."
            )
        self.oauth_token = token
        self.api_version = settings.swarm_api_version
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    # Core request helpers
    # ------------------------------------------------------------------ #

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.API_BASE}/{path.lstrip('/')}"
        query = params.copy() if params else {}
        query.update(
            {
                "oauth_token": self.oauth_token,
                "v": self.api_version,
            }
        )
        logger.debug("Swarm API GET %s params=%s", url, query)
        try:
            response = self.session.get(url, params=query, timeout=15)
        except requests.RequestException as exc:
            raise SwarmAPIError(f"Network error calling Swarm API: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover
            raise SwarmAPIError("Swarm API returned invalid JSON") from exc

        meta = data.get("meta", {})
        if meta.get("code") != 200:
            error_detail = meta.get("errorDetail") or meta.get("errorType") or "Unknown error"
            raise SwarmAPIError(f"Swarm API error ({meta.get('code')}): {error_detail}")

        return data.get("response", {})

    # ------------------------------------------------------------------ #
    # Public helpers
    # ------------------------------------------------------------------ #

    def get_self_checkins(
        self,
        limit: int = 5,
        after_timestamp: int | None = None,
        before_timestamp: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch the authenticated user's check-ins.

        Args:
            limit: Maximum number of check-ins to return (1-250)
            after_timestamp: Unix timestamp - only return check-ins after this time
            before_timestamp: Unix timestamp - only return check-ins before this time
        """
        params: dict[str, Any] = {
            "limit": max(1, min(limit, 250)),
            "sort": "newestfirst",
        }
        if after_timestamp is not None:
            params["afterTimestamp"] = after_timestamp
        if before_timestamp is not None:
            params["beforeTimestamp"] = before_timestamp

        response = self._request("users/self/checkins", params)
        return response.get("checkins", {}).get("items", [])

    def get_friends(self) -> list[SwarmUser]:
        response = self._request("users/self/friends", {"limit": 500})
        items = response.get("friends", {}).get("items", [])
        friends: list[SwarmUser] = []
        for item in items:
            name = _build_display_name(item)
            friends.append(SwarmUser(id=str(item.get("id")), display_name=name))
        return friends

    def get_user_checkins(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 50))
        path = "users/self/checkins" if user_id in {"self", "me"} else f"users/{user_id}/checkins"
        response = self._request(path, {"limit": limit, "sort": "newestfirst"})
        return response.get("checkins", {}).get("items", [])

    def find_user_by_name(self, query: str) -> SwarmUser:
        """Resolve a friend (or self) from a free-form name."""
        query = (query or "").strip().lower()
        if not query:
            raise ValueError("friend_name is required.")
        if query in {"me", "self"}:
            return SwarmUser(id="self", display_name="You")

        friends = self.get_friends()
        exact_match = next(
            (friend for friend in friends if friend.display_name.lower() == query),
            None,
        )
        if exact_match:
            return exact_match

        contains_match = [
            friend for friend in friends if query in friend.display_name.lower()
        ]
        if len(contains_match) == 1:
            return contains_match[0]
        if contains_match:
            options = ", ".join(friend.display_name for friend in contains_match[:5])
            raise ValueError(
                f"Multiple friends matched '{query}'. Please be more specific "
                f"(examples: {options})."
            )

        suggestions = ", ".join(friend.display_name for friend in friends[:10])
        raise ValueError(
            f"No Swarm friend matched '{query}'. "
            f"Available friends include: {suggestions or 'none'}."
        )


def describe_checkin(checkin: dict[str, Any], include_photos: bool = False) -> dict[str, Any]:
    """Normalize Swarm check-in JSON into a concise structure."""
    if not checkin:
        return {}
    venue = checkin.get("venue") or {}
    location = venue.get("location") or {}
    categories = [
        category.get("name")
        for category in venue.get("categories") or []
        if category.get("name")
    ]
    created_at = checkin.get("createdAt")
    iso_time = None
    relative_minutes = None
    if isinstance(created_at, (int, float)):
        dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
        iso_time = dt.isoformat()
        relative_minutes = int((datetime.now(tz=timezone.utc) - dt).total_seconds() // 60)

    # Photo information
    photos_data = checkin.get("photos") or {}
    photo_count = photos_data.get("count", 0)

    result = {
        "timestamp": created_at,
        "iso_time": iso_time,
        "minutes_since": relative_minutes,
        "venue_name": venue.get("name"),
        "city": location.get("city"),
        "state": location.get("state"),
        "country": location.get("country"),
        "latitude": location.get("lat"),
        "longitude": location.get("lng"),
        "canonical_url": venue.get("canonicalUrl"),
        "categories": categories,
        "shout": checkin.get("shout"),
        "photo_count": photo_count,
    }

    # Optionally include full photo URLs
    if include_photos and photo_count > 0:
        photo_urls = []
        for photo in photos_data.get("items", []):
            prefix = photo.get("prefix", "")
            suffix = photo.get("suffix", "")
            width = photo.get("width")
            height = photo.get("height")
            if prefix and suffix:
                # Use original size for best quality
                url = f"{prefix}original{suffix}"
                photo_urls.append({
                    "url": url,
                    "width": width,
                    "height": height,
                })
        result["photos"] = photo_urls

    return result


def _build_display_name(user: dict[str, Any]) -> str:
    first = user.get("firstName") or ""
    last = user.get("lastName") or ""
    username = user.get("username") or ""
    parts = [part for part in (first, last) if part]
    name = " ".join(parts).strip()
    if not name and username:
        name = username
    if not name:
        name = str(user.get("id", "Unknown"))
    return name

