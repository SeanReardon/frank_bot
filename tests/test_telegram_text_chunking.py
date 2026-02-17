from __future__ import annotations

from services.telegram_text import chunk_telegram_text


class TestChunkTelegramText:
    def test_short_text_single_chunk_no_header(self) -> None:
        res = chunk_telegram_text("hello", max_len=50)
        assert res.chunks == ["hello"]
        assert res.truncated is False

    def test_long_text_chunks_with_headers_and_round_trip(self) -> None:
        text = "a" * 2500
        res = chunk_telegram_text(text, max_len=500)
        assert len(res.chunks) > 1
        for chunk in res.chunks:
            assert len(chunk) <= 500
            assert chunk.startswith("(")  # "(i of n)"
            assert "\n" in chunk

        # Strip headers and confirm we can reconstruct the original content.
        rebuilt = "".join(c.split("\n", 1)[1] for c in res.chunks)
        assert rebuilt == text

    def test_prefers_newline_boundaries(self) -> None:
        # Force chunking while still allowing whole-line packing.
        text = "line1\nline2\nline3\nline4\nline5\n"
        res = chunk_telegram_text(text, max_len=25)

        # Header reduces available payload; with 6-char lines, we should pack
        # whole lines without splitting mid-line.
        payloads = [c.split("\n", 1)[1] for c in res.chunks]
        assert payloads == ["line1\nline2\n", "line3\nline4\n", "line5\n"]

    def test_max_chunks_truncates(self) -> None:
        text = "x" * 5000
        res = chunk_telegram_text(text, max_len=200, max_chunks=2)
        assert len(res.chunks) == 2
        assert res.truncated is True
