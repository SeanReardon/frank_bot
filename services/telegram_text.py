"""
Utilities for sending long text through Telegram.

Telegram hard-limits message text to 4096 characters. When Frank forwards
LLM/script output it can exceed that limit, so we chunk it into multiple
messages and (optionally) add a "(i of n)" header to each.
"""

from __future__ import annotations

from dataclasses import dataclass


TELEGRAM_MAX_TEXT_LEN = 4096


@dataclass(frozen=True)
class ChunkedText:
    chunks: list[str]
    truncated: bool = False


def _split_text_hard(text: str, *, max_len: int) -> list[str]:
    """
    Split text into chunks of at most max_len, preferring newline boundaries.

    This is intentionally simple and deterministic; callers can layer prefixes
    and other decorations on top.
    """
    if max_len <= 0:
        raise ValueError("max_len must be > 0")

    if not text:
        return [""]

    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    buf = ""

    # Greedy line-based packing to preserve readability.
    for line in text.splitlines(keepends=True):
        # If a single line is too long, flush current buffer and hard-split it.
        if len(line) > max_len:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(line), max_len):
                chunks.append(line[i:i + max_len])
            continue

        # Otherwise, pack line into the current buffer.
        if buf and (len(buf) + len(line) > max_len):
            chunks.append(buf)
            buf = ""
        buf += line

    if buf:
        chunks.append(buf)

    # Defensive: ensure no chunk exceeds max_len.
    final: list[str] = []
    for c in chunks:
        if len(c) <= max_len:
            final.append(c)
            continue
        for i in range(0, len(c), max_len):
            final.append(c[i:i + max_len])
    return final


def chunk_telegram_text(
    text: str,
    *,
    max_len: int = TELEGRAM_MAX_TEXT_LEN,
    add_part_headers: bool = True,
    max_chunks: int = 50,
) -> ChunkedText:
    """
    Chunk text for Telegram sending.

    - If the text fits, returns a single chunk without any header.
    - If it doesn't fit, splits into multiple chunks (<= max_len) and prefixes
      each with "(i of n)\\n" so the receiver knows what to expect.
    - If the chunk count would exceed max_chunks, truncates the payload.
    """
    if max_chunks <= 0:
        raise ValueError("max_chunks must be > 0")

    if not text:
        return ChunkedText(chunks=[""])

    # First pass: split without headers.
    chunks = _split_text_hard(text, max_len=max_len)
    if len(chunks) == 1 or not add_part_headers:
        return ChunkedText(chunks=chunks)

    # Iteratively re-split accounting for header length based on total parts.
    # Header length depends on number of digits in n; compute using worst-case.
    for _ in range(5):  # converges very quickly
        n = len(chunks)
        header_len = len(f"({n} of {n})\n")
        available = max_len - header_len
        if available <= 0:
            raise ValueError("max_len too small to fit part headers")

        new_chunks = _split_text_hard(text, max_len=available)
        if len(new_chunks) == len(chunks):
            chunks = new_chunks
            break
        chunks = new_chunks

    n = len(chunks)
    with_headers = [
        f"({i} of {n})\n{chunk}" for i, chunk in enumerate(chunks, start=1)
    ]

    truncated = False
    if len(with_headers) > max_chunks:
        truncated = True
        with_headers = with_headers[: max_chunks]
        # Best-effort marker; keep within limit.
        last = with_headers[-1]
        marker = "\n\n[truncated]"
        if len(last) + len(marker) <= max_len:
            with_headers[-1] = last + marker
        else:
            # Replace tail to guarantee we stay within the limit.
            available = max(0, max_len - len(marker))
            with_headers[-1] = (last[:available] + marker)[:max_len]

    # Enforce length invariant.
    with_headers = [c[:max_len] for c in with_headers]
    return ChunkedText(chunks=with_headers, truncated=truncated)
