from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.android_client import AndroidClient, ADBResult


@pytest.mark.asyncio
async def test_get_screen_size_parses_wm_size_output() -> None:
    client = AndroidClient(host="192.0.2.10", port=5555, serial=None)
    client._run_adb = AsyncMock(
        return_value=ADBResult(success=True, output="Physical size: 1000x2000\n")
    )

    size = await client.get_screen_size(cache_ttl_seconds=0)
    assert size == (1000, 2000)


def test_parse_ui_elements_handles_non_self_closing_nodes() -> None:
    client = AndroidClient(host="192.0.2.10", port=5555, serial=None)
    xml = (
        "<hierarchy>"
        "<node text=\"A\" clickable=\"true\" bounds=\"[0,0][10,10]\"></node>"
        "</hierarchy>"
    )
    els = client.parse_ui_elements(xml)
    assert len(els) == 1
    assert els[0].text == "A"
    assert els[0].clickable is True
    assert els[0].bounds == (0, 0, 10, 10)
