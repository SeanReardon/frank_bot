#!/usr/bin/env python
"""
CLI script for generating SEAN.md style guide from Telegram message history.

This script fetches Sean's outgoing messages from a Telegram chat (default:
@MagicConciergeBot), analyzes communication patterns, and generates a style
guide document that can be used by AI systems to mimic Sean's voice.

Usage:
    poetry run python scripts/generate_sean_md.py [options]

Options:
    --chat-id CHAT    Chat to analyze (default: @MagicConciergeBot)
    --before-date DATE Only analyze messages before this date (default: 2026-01-01)
    --output FILE      Output file path (default: ./SEAN.md)
    --send             Send the generated content to @SeanReardon via Telegram

Requirements:
    Set the following environment variables (or .env file):
    - TELEGRAM_API_ID: Your Telegram API ID
    - TELEGRAM_API_HASH: Your Telegram API hash
    - TELEGRAM_PHONE: Your phone number in E.164 format
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate SEAN.md style guide from Telegram message history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate SEAN.md from Magic conversation
    poetry run python scripts/generate_sean_md.py

    # Analyze a different chat
    poetry run python scripts/generate_sean_md.py --chat-id @OtherBot

    # Generate and send to Sean
    poetry run python scripts/generate_sean_md.py --send

    # Output to custom path
    poetry run python scripts/generate_sean_md.py --output /tmp/sean_style.md
        """,
    )

    parser.add_argument(
        "--chat-id",
        default="@MagicConciergeBot",
        help="Telegram chat to analyze (default: @MagicConciergeBot)",
    )
    parser.add_argument(
        "--before-date",
        default="2026-01-01",
        help="Only analyze messages before this date (default: 2026-01-01)",
    )
    parser.add_argument(
        "--output",
        default="./SEAN.md",
        help="Output file path (default: ./SEAN.md)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send generated content to @SeanReardon via Telegram",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime."""
    # Try ISO format first
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        pass

    # Try simple date format
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD or ISO format.")


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Import after path setup
    from services.telegram_client import TelegramClientService
    from services.style_analyzer import StyleAnalyzer

    # Check configuration
    telegram = TelegramClientService()
    if not telegram.is_configured:
        print("Error: Telegram is not configured.")
        print("Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE.")
        return 1

    # Parse before_date
    try:
        before_date = parse_date(args.before_date)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print(f"SEAN.md Generator")
    print(f"=" * 40)
    print(f"Chat: {args.chat_id}")
    print(f"Before: {before_date.strftime('%Y-%m-%d')}")
    print(f"Output: {args.output}")
    print()

    # Step 1: Fetch messages
    print("Fetching messages...", end=" ", flush=True)
    analyzer = StyleAnalyzer(telegram_service=telegram)

    try:
        messages = await analyzer.fetch_authentic_messages(
            chat_id=args.chat_id,
            before_date=before_date,
        )
    except Exception as e:
        print(f"FAILED")
        print(f"Error fetching messages: {e}")
        return 1

    print(f"Found {len(messages)} messages")

    if not messages:
        print("Error: No outgoing messages found.")
        print(f"Make sure you have sent messages to {args.chat_id}.")
        return 1

    # Step 2: Analyze patterns
    print("Analyzing patterns...", end=" ", flush=True)
    result = analyzer.analyze_patterns(messages)

    total_patterns = sum(len(cat.patterns) for cat in result.all_categories())
    print(f"Found {total_patterns} patterns")

    # Display pattern summary
    print("\nPattern summary:")
    for category in result.all_categories():
        if category.patterns:
            print(f"  - {category.name}: {len(category.patterns)} examples")

    # Step 3: Generate SEAN.md
    print("\nGenerating SEAN.md...", end=" ", flush=True)
    content = analyzer.generate_sean_md(result)
    print(f"{len(content)} characters")

    # Step 4: Write to file
    print(f"Writing to {args.output}...", end=" ", flush=True)
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        print("Done!")
    except Exception as e:
        print(f"FAILED")
        print(f"Error writing file: {e}")
        return 1

    # Step 5: Optionally send to Sean
    if args.send:
        print(f"\nSending to @SeanReardon...", end=" ", flush=True)

        # Split content if it exceeds Telegram's limit
        TELEGRAM_LIMIT = 4096
        if len(content) <= TELEGRAM_LIMIT:
            chunks = [content]
        else:
            # Split at paragraph boundaries
            chunks = []
            current = ""
            for para in content.split("\n\n"):
                if len(current) + len(para) + 2 > TELEGRAM_LIMIT:
                    if current:
                        chunks.append(current.strip())
                        current = ""
                    # Handle oversized paragraphs
                    while len(para) > TELEGRAM_LIMIT:
                        chunks.append(para[:TELEGRAM_LIMIT])
                        para = para[TELEGRAM_LIMIT:]
                    current = para
                else:
                    current = (current + "\n\n" + para).strip()
            if current:
                chunks.append(current)

        try:
            for i, chunk in enumerate(chunks, 1):
                if len(chunks) > 1:
                    prefix = f"[SEAN.md Part {i}/{len(chunks)}]\n\n"
                    chunk = prefix + chunk

                result = await telegram.send_message("@SeanReardon", chunk)
                if not result.success:
                    print(f"FAILED")
                    print(f"Error sending message {i}/{len(chunks)}: {result.error}")
                    return 1

            print(f"Sent {len(chunks)} message(s)")
        except Exception as e:
            print(f"FAILED")
            print(f"Error sending: {e}")
            return 1

    print("\nDone!")
    return 0


if __name__ == "__main__":
    # Load .env if available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    sys.exit(asyncio.run(main()))
