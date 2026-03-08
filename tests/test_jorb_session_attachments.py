from __future__ import annotations

import base64
from pathlib import Path

from services.jorb_session import _build_user_content


def test_build_user_content_includes_text_context() -> None:
    event_context = {
        "channel": "telegram_bot",
        "sender": "@SeanReardon",
        "sender_name": "Sean Reardon",
        "content": "do you see this?",
        "timestamp": "2026-03-08T00:00:00+00:00",
        "message_count": 1,
        "attachments": [],
    }

    blocks = _build_user_content(event_context)

    assert len(blocks) == 1
    assert blocks[0]["type"] == "text"
    assert "do you see this?" in blocks[0]["text"]


def test_build_user_content_embeds_image_attachments(tmp_path: Path) -> None:
    image_path = tmp_path / "incoming.png"
    png_bytes = b"\x89PNG\r\n\x1a\nfake"
    image_path.write_bytes(png_bytes)

    event_context = {
        "channel": "telegram_bot",
        "sender": "@SeanReardon",
        "sender_name": "Sean Reardon",
        "content": "can you read this screenshot?",
        "timestamp": "2026-03-08T00:00:00+00:00",
        "message_count": 1,
        "attachments": [
            {
                "kind": "image",
                "path": str(image_path),
                "mime_type": "image/png",
            }
        ],
    }

    blocks = _build_user_content(event_context)

    assert len(blocks) == 2
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")
    )
