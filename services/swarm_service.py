"""
Helpers for interacting with the Swarm/Foursquare API.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from config import get_settings
from services.stats import stats

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 1.0  # seconds


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
                "Swarm is not configured. "
                "Configure Vault secret `secret/frank-bot/swarm` "
                "(oauth_token, api_key), or for local/dev runs without Vault "
                "set SWARM_OAUTH_TOKEN."
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

        # Log request details (mask token for security)
        log_params = {k: v for k, v in query.items() if k != "oauth_token"}
        log_params["oauth_token"] = "***"
        logger.info("SWARM_REQUEST: %s params=%s", path, log_params)

        last_error: Exception | None = None
        swarm_stats = stats.get_service_stats("swarm")

        for attempt in range(MAX_RETRIES):
            start_time = time.time()
            try:
                response = self.session.get(url, params=query, timeout=15)
                elapsed_ms = (time.time() - start_time) * 1000
                response_bytes = len(response.content)

                logger.info(
                    "SWARM_RESPONSE: %s status=%d elapsed=%.0fms attempt=%d",
                    path, response.status_code, elapsed_ms, attempt + 1
                )

                try:
                    data = response.json()
                except ValueError as exc:
                    logger.error("SWARM_ERROR: %s invalid JSON response", path)
                    swarm_stats.record_request(elapsed_ms, success=False, error="Invalid JSON response")
                    stats.record_error("swarm", "Invalid JSON response", {"path": path})
                    raise SwarmAPIError("Swarm API returned invalid JSON") from exc

                meta = data.get("meta", {})
                if meta.get("code") != 200:
                    error_detail = meta.get("errorDetail") or meta.get("errorType") or "Unknown error"
                    error_code = meta.get("code")
                    logger.warning(
                        "SWARM_API_ERROR: %s code=%s detail=%s attempt=%d",
                        path, error_code, error_detail, attempt + 1
                    )

                    # Retry on server errors (5xx) or rate limits (429)
                    if error_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                        sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.info("SWARM_RETRY: sleeping %.1fs before retry", sleep_time)
                        time.sleep(sleep_time)
                        continue

                    swarm_stats.record_request(elapsed_ms, success=False, error=f"{error_code}: {error_detail}")
                    stats.record_error("swarm", f"API error: {error_detail}", {"path": path, "code": error_code})
                    raise SwarmAPIError(f"Swarm API error ({error_code}): {error_detail}")

                # Record successful request
                swarm_stats.record_request(elapsed_ms, success=True, bytes_received=response_bytes)

                # Log success with result summary
                response_data = data.get("response", {})
                checkins = response_data.get("checkins", {})
                if checkins:
                    item_count = len(checkins.get("items", []))
                    logger.info("SWARM_SUCCESS: %s returned %d checkins", path, item_count)
                else:
                    logger.info("SWARM_SUCCESS: %s", path)

                return response_data

            except requests.RequestException as exc:
                elapsed_ms = (time.time() - start_time) * 1000
                last_error = exc
                logger.warning(
                    "SWARM_NETWORK_ERROR: %s error=%s attempt=%d",
                    path, str(exc), attempt + 1
                )

                if attempt < MAX_RETRIES - 1:
                    sleep_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                    logger.info("SWARM_RETRY: sleeping %.1fs before retry", sleep_time)
                    time.sleep(sleep_time)
                    continue

                swarm_stats.record_request(elapsed_ms, success=False, error=f"Network error: {exc}")
                stats.record_error("swarm", f"Network error: {exc}", {"path": path})
                raise SwarmAPIError(f"Network error calling Swarm API: {exc}") from exc

        # Should not reach here, but just in case
        raise SwarmAPIError(f"Swarm API failed after {MAX_RETRIES} attempts: {last_error}")

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

