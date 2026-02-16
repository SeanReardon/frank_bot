"""
Tests for AndroidClient connect/disconnect behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.android_client import AndroidClient, ADBResult


@pytest.mark.asyncio
async def test_tcp_connect_uses_global_adb() -> None:
    """TCP/IP connect must run `adb connect` without `-s` selection."""
    client = AndroidClient(host="192.0.2.10", port=5555, serial=None)
    client._run_adb_global = AsyncMock(
        return_value=ADBResult(success=True, output="connected")
    )

    result = await client.connect()

    assert result.success is True
    client._run_adb_global.assert_awaited_once_with(
        "connect",
        "192.0.2.10:5555",
    )


@pytest.mark.asyncio
async def test_tcp_connect_treats_already_connected_as_success() -> None:
    """Even when adb reports already connected, connect() should be success."""
    client = AndroidClient(host="192.0.2.10", port=5555, serial=None)
    client._run_adb_global = AsyncMock(
        return_value=ADBResult(
            success=False,
            output="already connected to 192.0.2.10:5555",
        )
    )

    result = await client.connect()

    assert result.success is True


@pytest.mark.asyncio
async def test_tcp_disconnect_uses_global_adb() -> None:
    """TCP/IP disconnect must run `adb disconnect` without `-s` selection."""
    client = AndroidClient(host="192.0.2.10", port=5555, serial=None)
    client._run_adb_global = AsyncMock(
        return_value=ADBResult(success=True, output="disconnected")
    )

    result = await client.disconnect()

    assert result.success is True
    client._run_adb_global.assert_awaited_once_with(
        "disconnect",
        "192.0.2.10:5555",
    )
