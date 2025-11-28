"""
Small helper to fetch accurate UTC time from NTP (pool.ntp.org).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

import ntplib


logger = logging.getLogger(__name__)
NTP_SERVER: Final[str] = "pool.ntp.org"


def fetch_utc_now() -> datetime | None:
    """Return a datetime from NTP or None on failure."""
    client = ntplib.NTPClient()
    try:
        response = client.request(NTP_SERVER, version=3, timeout=5)
    except Exception:
        logger.warning("Unable to reach NTP server %s", NTP_SERVER, exc_info=True)
        return None
    return datetime.fromtimestamp(response.tx_time, tz=timezone.utc)


__all__ = ["fetch_utc_now"]

