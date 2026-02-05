"""
Tests for the rate limiter service.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, "/home/claudia/dev/frank_bot")

from services.rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    reset_rate_limiter,
    get_android_rate_limiter,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_config(self) -> None:
        """Default config has reasonable values."""
        config = RateLimitConfig()
        assert config.requests_per_minute == 10
        assert config.requests_per_hour == 100

    def test_custom_config(self) -> None:
        """Custom config values are respected."""
        config = RateLimitConfig(requests_per_minute=5, requests_per_hour=50)
        assert config.requests_per_minute == 5
        assert config.requests_per_hour == 50


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_allows_requests_within_limit(self) -> None:
        """Allows requests within rate limits."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=5, requests_per_hour=100))

        # First 5 requests should be allowed
        for i in range(5):
            allowed, info = limiter.check_rate_limit(api_key="test-key")
            assert allowed, f"Request {i+1} should be allowed"
            assert info["retry_after"] == 0

    def test_blocks_requests_over_per_minute_limit(self) -> None:
        """Blocks requests that exceed per-minute limit."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=3, requests_per_hour=100))

        # Use up the limit
        for _ in range(3):
            allowed, _ = limiter.check_rate_limit(api_key="test-key")
            assert allowed

        # Next request should be blocked
        allowed, info = limiter.check_rate_limit(api_key="test-key")
        assert not allowed
        assert info["limit_type"] == "per-minute"
        assert info["retry_after"] > 0
        assert info["minute_remaining"] == 0

    def test_blocks_requests_over_hourly_limit(self) -> None:
        """Blocks requests that exceed hourly limit."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=100, requests_per_hour=5))

        # Use up the hourly limit
        for _ in range(5):
            allowed, _ = limiter.check_rate_limit(api_key="test-key")
            assert allowed

        # Next request should be blocked by hourly limit
        allowed, info = limiter.check_rate_limit(api_key="test-key")
        assert not allowed
        assert info["limit_type"] == "hourly"
        assert info["retry_after"] > 0
        assert info["hour_remaining"] == 0

    def test_long_running_exempt_from_minute_limit(self) -> None:
        """Long-running tasks exempt from per-minute limit."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=2, requests_per_hour=100))

        # Use up the per-minute limit
        for _ in range(2):
            allowed, _ = limiter.check_rate_limit(api_key="test-key")
            assert allowed

        # Regular request should be blocked
        allowed, _ = limiter.check_rate_limit(api_key="test-key", is_long_running=False)
        assert not allowed

        # But long-running should be allowed (exempt from per-minute)
        allowed, info = limiter.check_rate_limit(api_key="test-key", is_long_running=True)
        assert allowed
        assert info["hour_remaining"] > 0

    def test_long_running_still_counts_toward_hourly(self) -> None:
        """Long-running tasks still count toward hourly limit."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=100, requests_per_hour=3))

        # Use up hourly limit with long-running tasks
        for _ in range(3):
            allowed, _ = limiter.check_rate_limit(api_key="test-key", is_long_running=True)
            assert allowed

        # Should now be blocked by hourly limit
        allowed, info = limiter.check_rate_limit(api_key="test-key", is_long_running=True)
        assert not allowed
        assert info["limit_type"] == "hourly"

    def test_separate_limits_per_api_key(self) -> None:
        """Different API keys have separate rate limits."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=2, requests_per_hour=100))

        # Use up limit for key1
        for _ in range(2):
            limiter.check_rate_limit(api_key="key1")

        # key1 should be blocked
        allowed, _ = limiter.check_rate_limit(api_key="key1")
        assert not allowed

        # key2 should still be allowed
        allowed, _ = limiter.check_rate_limit(api_key="key2")
        assert allowed

    def test_anonymous_requests_share_bucket(self) -> None:
        """Anonymous requests (no API key) share a bucket."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=2, requests_per_hour=100))

        # Use up limit for anonymous
        for _ in range(2):
            limiter.check_rate_limit(api_key=None)

        # Next anonymous should be blocked
        allowed, _ = limiter.check_rate_limit(api_key=None)
        assert not allowed

    def test_tokens_refill_over_time(self) -> None:
        """Tokens refill over time."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=6, requests_per_hour=100))
        # 6 per minute = 1 per 10 seconds

        # Use up the limit
        for _ in range(6):
            limiter.check_rate_limit(api_key="test-key")

        # Should be blocked
        allowed, _ = limiter.check_rate_limit(api_key="test-key")
        assert not allowed

        # Manually advance time by faking the bucket's last_update
        bucket = limiter._get_bucket("test-key", "minute")
        bucket.last_update -= 20  # Simulate 20 seconds passing

        # Refill happens on next check, should now have ~2 tokens
        allowed, info = limiter.check_rate_limit(api_key="test-key")
        assert allowed  # Should be allowed now

    def test_get_usage_returns_remaining_tokens(self) -> None:
        """get_usage returns current remaining tokens."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=10, requests_per_hour=100))

        # Initial usage
        usage = limiter.get_usage(api_key="test-key")
        assert usage["minute_remaining"] == 10
        assert usage["hour_remaining"] == 100
        assert usage["minute_limit"] == 10
        assert usage["hour_limit"] == 100

        # After some requests
        for _ in range(3):
            limiter.check_rate_limit(api_key="test-key")

        usage = limiter.get_usage(api_key="test-key")
        assert usage["minute_remaining"] == 7
        assert usage["hour_remaining"] == 97

    def test_returns_429_info_on_block(self) -> None:
        """Returns retry-after and remaining info on block."""
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=1, requests_per_hour=100))

        # Use up the limit
        limiter.check_rate_limit(api_key="test-key")

        # Next request should return 429 info
        allowed, info = limiter.check_rate_limit(api_key="test-key")
        assert not allowed
        assert "retry_after" in info
        assert info["retry_after"] > 0
        assert "minute_remaining" in info
        assert "hour_remaining" in info


class TestGetAndroidRateLimiter:
    """Tests for get_android_rate_limiter singleton."""

    def test_returns_singleton_instance(self) -> None:
        """Returns the same instance on multiple calls."""
        reset_rate_limiter()

        with patch("config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_rate_limit_minute=10,
                android_rate_limit_hour=100,
            )

            limiter1 = get_android_rate_limiter()
            limiter2 = get_android_rate_limiter()

            assert limiter1 is limiter2

    def test_uses_settings_config(self) -> None:
        """Uses config from settings."""
        reset_rate_limiter()

        with patch("config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_rate_limit_minute=5,
                android_rate_limit_hour=50,
            )

            limiter = get_android_rate_limiter()

            assert limiter.config.requests_per_minute == 5
            assert limiter.config.requests_per_hour == 50

    def test_reset_clears_singleton(self) -> None:
        """reset_rate_limiter clears the singleton."""
        reset_rate_limiter()

        with patch("config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                android_rate_limit_minute=10,
                android_rate_limit_hour=100,
            )

            limiter1 = get_android_rate_limiter()
            reset_rate_limiter()
            limiter2 = get_android_rate_limiter()

            assert limiter1 is not limiter2
