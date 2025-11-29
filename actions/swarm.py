"""
Swarm/Foursquare actions: search checkins.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from actions.helpers import coerce_bool, coerce_int, fuzzy_name_match
from services.swarm_service import SwarmService, describe_checkin

logger = logging.getLogger(__name__)


async def search_checkins_action(
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Search your Swarm check-ins with optional filtering.

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
    max_results = coerce_int(
        args.get("max_results"),
        10,
        minimum=1,
        maximum=250,
    )
    stale_minutes = coerce_int(
        args.get("stale_minutes"),
        180,
        minimum=5,
        maximum=1440,
    )

    # Date filtering
    year = args.get("year")
    after_date = args.get("after_date")  # ISO date string YYYY-MM-DD
    before_date = args.get("before_date")  # ISO date string YYYY-MM-DD

    # Companion filtering - can be a single name, comma-separated names, or list of names
    # Default is OR logic (any match), use companion_match=all for AND logic
    with_companion = args.get("with_companion")
    companion_names: list[str] = []
    if with_companion:
        if isinstance(with_companion, str):
            # Support comma-separated names: "lauren, ekaterina"
            companion_names = [
                name.strip().lower()
                for name in with_companion.split(",")
                if name.strip()
            ]
        else:
            companion_names = [name.strip().lower() for name in with_companion if name]

    # "any" = OR logic (default), "all" = AND logic (all companions must be present)
    companion_match = (args.get("companion_match") or "any").strip().lower()

    # If only_with_companions is true, filter to only checkins that have companions
    only_with_companions = coerce_bool(args.get("only_with_companions"))

    # Category filtering
    category_filter = (args.get("category") or "").strip().lower()

    # Photo filtering
    has_photos = coerce_bool(args.get("has_photos"))  # Filter to only checkins with photos
    include_photos = coerce_bool(args.get("include_photos"))  # Include photo URLs in response

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
        needs_filtering = companion_names or only_with_companions or category_filter or has_photos

        # For filtered searches, paginate through more results to find enough matches.
        # Limit to 40 batches (10,000 check-ins max) to cover all-time searches.
        max_batches = 40 if needs_filtering else 1
        batch_size = 250

        # Log search parameters
        logger.info(
            "CHECKIN_SEARCH: companions=%s match=%s category=%s has_photos=%s "
            "after=%s before=%s max_results=%d",
            companion_names, companion_match, category_filter, has_photos,
            after_timestamp, before_timestamp, max_results
        )

        entries: list[dict[str, Any]] = []
        current_before_timestamp = before_timestamp
        total_scanned = 0
        total_filtered_out = 0

        for batch_num in range(max_batches):
            checkins_raw = service.get_self_checkins(
                limit=batch_size,
                after_timestamp=after_timestamp,
                before_timestamp=current_before_timestamp,
            )

            if not checkins_raw:
                logger.info(
                    "CHECKIN_SEARCH_DONE: batch=%d scanned=%d filtered_out=%d matched=%d (no more data)",
                    batch_num + 1, total_scanned, total_filtered_out, len(entries)
                )
                break  # No more check-ins

            batch_scanned = len(checkins_raw)
            total_scanned += batch_scanned

            # Process this batch
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

                # Filter by companion names if specified (fuzzy matching)
                if companion_names:
                    def companion_matches(query_name: str) -> bool:
                        return any(
                            fuzzy_name_match(query_name, c["display_name"])
                            or fuzzy_name_match(query_name, c["first_name"] or "")
                            or fuzzy_name_match(query_name, c["last_name"] or "")
                            for c in companions
                        )

                    if companion_match == "all":
                        # AND logic: ALL requested companions must be present
                        if not all(companion_matches(name) for name in companion_names):
                            continue
                    else:
                        # OR logic (default): ANY requested companion matches
                        if not any(companion_matches(name) for name in companion_names):
                            continue

                # Filter to only checkins with companions
                if only_with_companions and not companions:
                    continue

                # Extract venue info (include photos if requested)
                info = describe_checkin(item, include_photos=include_photos)
                categories = info.get("categories") or []
                photo_count = info.get("photo_count", 0)

                # Filter by category
                if category_filter:
                    category_match_found = any(
                        category_filter in cat.lower() for cat in categories
                    )
                    if not category_match_found:
                        continue

                # Filter to only checkins with photos
                if has_photos and photo_count == 0:
                    continue

                entry = {
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
                    "photo_count": photo_count,
                }

                # Include photo URLs if requested
                if include_photos and info.get("photos"):
                    entry["photos"] = info["photos"]

                entries.append(entry)

                if len(entries) >= max_results:
                    break

            # Log batch progress
            batch_matched = len(entries) - (total_scanned - batch_scanned - total_filtered_out)
            logger.debug(
                "CHECKIN_BATCH: batch=%d scanned=%d total_matched=%d",
                batch_num + 1, batch_scanned, len(entries)
            )

            # Check if we have enough results
            if len(entries) >= max_results:
                logger.info(
                    "CHECKIN_SEARCH_DONE: batches=%d scanned=%d matched=%d (reached max_results)",
                    batch_num + 1, total_scanned, len(entries)
                )
                break

            # Get timestamp of oldest check-in for next batch
            oldest_checkin = checkins_raw[-1]
            oldest_ts = oldest_checkin.get("createdAt")
            if oldest_ts:
                # Fetch check-ins before this timestamp in next batch
                current_before_timestamp = oldest_ts
            else:
                logger.info(
                    "CHECKIN_SEARCH_DONE: batches=%d scanned=%d matched=%d (no timestamp for pagination)",
                    batch_num + 1, total_scanned, len(entries)
                )
                break  # Can't paginate without timestamp
        else:
            # Exhausted all batches
            logger.info(
                "CHECKIN_SEARCH_DONE: batches=%d scanned=%d matched=%d (max batches reached)",
                max_batches, total_scanned, len(entries)
            )

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
        joiner = " and " if companion_match == "all" else " or "
        filters_desc.append(f"with {joiner.join(companion_names)}")
    elif only_with_companions:
        filters_desc.append("with companions")

    if category_filter:
        filters_desc.append(f"in '{category_filter}' venues")

    if has_photos:
        filters_desc.append("with photos")

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
            "has_photos": has_photos,
            "include_photos": include_photos,
        },
    }


__all__ = ["search_checkins_action"]
