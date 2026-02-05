"""
Rate limiter for Android phone actions.

Implements a token bucket algorithm with both per-minute and per-hour limits.
Tracks usage per API key (or shared for unauthenticated requests).
"""

from __future__ import annotations

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    tokens: float
    last_update: float = field(default_factory=time.time)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_minute: int = 10
    requests_per_hour: int = 100


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.

    Tracks both per-minute and per-hour limits per API key.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration. Uses defaults if not provided.
        """
        self._config = config or RateLimitConfig()
        # Buckets keyed by (api_key, window_type)
        # window_type is "minute" or "hour"
        self._buckets: dict[tuple[str, str], RateLimitBucket] = defaultdict(
            lambda: RateLimitBucket(tokens=0)
        )
        self._lock_free_updates = True  # For single-threaded async usage

    @property
    def config(self) -> RateLimitConfig:
        """Get rate limit configuration."""
        return self._config

    def _get_bucket(self, api_key: str, window_type: str) -> RateLimitBucket:
        """Get or create bucket for given key and window type."""
        key = (api_key or "_anonymous", window_type)
        if key not in self._buckets:
            # Initialize with full capacity
            if window_type == "minute":
                self._buckets[key] = RateLimitBucket(tokens=self._config.requests_per_minute)
            else:
                self._buckets[key] = RateLimitBucket(tokens=self._config.requests_per_hour)
        return self._buckets[key]

    def _refill_bucket(self, bucket: RateLimitBucket, window_type: str) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_update

        if window_type == "minute":
            # Refill rate: requests_per_minute tokens per 60 seconds
            max_tokens = self._config.requests_per_minute
            refill_rate = max_tokens / 60.0
        else:
            # Refill rate: requests_per_hour tokens per 3600 seconds
            max_tokens = self._config.requests_per_hour
            refill_rate = max_tokens / 3600.0

        # Add tokens based on elapsed time
        bucket.tokens = min(max_tokens, bucket.tokens + elapsed * refill_rate)
        bucket.last_update = now

    def check_rate_limit(
        self,
        api_key: str | None = None,
        is_long_running: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Check if request is allowed under rate limits.

        Args:
            api_key: API key for the request (None for anonymous)
            is_long_running: If True, exempt from per-minute limit
                           but still count toward hourly limit

        Returns:
            Tuple of (allowed: bool, info: dict)
            info contains:
                - retry_after: seconds until next request allowed (if denied)
                - minute_remaining: requests remaining this minute
                - hour_remaining: requests remaining this hour
        """
        key = api_key or "_anonymous"

        # Get buckets
        minute_bucket = self._get_bucket(key, "minute")
        hour_bucket = self._get_bucket(key, "hour")

        # Refill based on elapsed time
        self._refill_bucket(minute_bucket, "minute")
        self._refill_bucket(hour_bucket, "hour")

        # Check hourly limit (always applies)
        if hour_bucket.tokens < 1:
            # Calculate retry_after for hourly bucket
            tokens_needed = 1 - hour_bucket.tokens
            refill_rate = self._config.requests_per_hour / 3600.0
            retry_after = tokens_needed / refill_rate if refill_rate > 0 else 3600

            logger.warning(
                "Rate limit exceeded (hourly) for key=%s: %d remaining",
                key[:8] + "..." if len(key) > 8 else key,
                int(hour_bucket.tokens),
            )

            return False, {
                "retry_after": int(retry_after) + 1,
                "minute_remaining": int(minute_bucket.tokens),
                "hour_remaining": 0,
                "limit_type": "hourly",
            }

        # Check per-minute limit (unless long-running task)
        if not is_long_running and minute_bucket.tokens < 1:
            # Calculate retry_after for minute bucket
            tokens_needed = 1 - minute_bucket.tokens
            refill_rate = self._config.requests_per_minute / 60.0
            retry_after = tokens_needed / refill_rate if refill_rate > 0 else 60

            logger.warning(
                "Rate limit exceeded (per-minute) for key=%s: %d remaining",
                key[:8] + "..." if len(key) > 8 else key,
                int(minute_bucket.tokens),
            )

            return False, {
                "retry_after": int(retry_after) + 1,
                "minute_remaining": 0,
                "hour_remaining": int(hour_bucket.tokens),
                "limit_type": "per-minute",
            }

        # Allowed - consume tokens
        if not is_long_running:
            minute_bucket.tokens -= 1
        hour_bucket.tokens -= 1

        return True, {
            "retry_after": 0,
            "minute_remaining": int(minute_bucket.tokens),
            "hour_remaining": int(hour_bucket.tokens),
        }

    def get_usage(self, api_key: str | None = None) -> dict[str, Any]:
        """
        Get current usage stats for an API key.

        Returns:
            Dict with minute_remaining and hour_remaining
        """
        key = api_key or "_anonymous"

        minute_bucket = self._get_bucket(key, "minute")
        hour_bucket = self._get_bucket(key, "hour")

        # Refill before reporting
        self._refill_bucket(minute_bucket, "minute")
        self._refill_bucket(hour_bucket, "hour")

        return {
            "minute_remaining": int(minute_bucket.tokens),
            "hour_remaining": int(hour_bucket.tokens),
            "minute_limit": self._config.requests_per_minute,
            "hour_limit": self._config.requests_per_hour,
        }


# Module-level singleton
_rate_limiter: RateLimiter | None = None


def get_android_rate_limiter() -> RateLimiter:
    """Get the global Android phone rate limiter instance."""
    global _rate_limiter

    if _rate_limiter is None:
        from config import get_settings

        settings = get_settings()
        config = RateLimitConfig(
            requests_per_minute=settings.android_rate_limit_minute,
            requests_per_hour=settings.android_rate_limit_hour,
        )
        _rate_limiter = RateLimiter(config)

    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None
