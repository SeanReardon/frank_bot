#!/usr/bin/env python3
"""
Test script for the enhanced Swarm check-ins API.

Tests filtering by:
  - Date range (year, after_date, before_date)
  - Companions (with_companion, only_with_companions)
  - Category
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

# These are live/integration-style tests; skip unless Swarm creds are present.
pytestmark = pytest.mark.skipif(
    not os.getenv("SWARM_OAUTH_TOKEN"),
    reason="Swarm is not configured (set SWARM_OAUTH_TOKEN to run these tests).",
)

# Add the project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from actions.swarm import search_checkins_action


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def test_recent_checkins():
    """Test basic recent check-ins."""
    print_header("TEST 1: Recent Check-ins (no filters)")

    result = await search_checkins_action({"max_results": 5})
    print(f"\n✓ {result['message']}")

    for checkin in result["checkins"]:
        venue = checkin["venue"]["name"]
        companions = [c["first_name"] for c in checkin.get("companions", [])]
        date = checkin["iso_time"][:10]
        companion_str = f" (with {', '.join(companions)})" if companions else ""
        print(f"  - {date}: {venue}{companion_str}")

    return True


async def test_year_filter():
    """Test filtering by year."""
    print_header("TEST 2: Check-ins from 2024")

    result = await search_checkins_action({
        "year": 2024,
        "max_results": 5,
    })
    print(f"\n✓ {result['message']}")
    print(f"  Filters applied: {result['filters']}")

    for checkin in result["checkins"]:
        venue = checkin["venue"]["name"]
        date = checkin["iso_time"][:10]
        print(f"  - {date}: {venue}")

    return True


async def test_companion_filter():
    """Test filtering by companion name."""
    print_header("TEST 3: Check-ins with a specific companion")

    # First, find a companion from recent checkins
    recent = await search_checkins_action({
        "only_with_companions": True,
        "max_results": 10,
    })

    if not recent["checkins"]:
        print("\n⚠️  No check-ins with companions found")
        return True

    # Get the first companion name
    first_checkin_with_companion = recent["checkins"][0]
    companion_name = first_checkin_with_companion["companions"][0]["first_name"]
    print(f"\n  Found companion: {companion_name}")

    # Now filter by that companion
    result = await search_checkins_action({
        "with_companion": companion_name,
        "max_results": 5,
    })
    print(f"\n✓ {result['message']}")

    for checkin in result["checkins"]:
        venue = checkin["venue"]["name"]
        date = checkin["iso_time"][:10]
        companions = [c["first_name"] for c in checkin.get("companions", [])]
        print(f"  - {date}: {venue} (with {', '.join(companions)})")

    return True


async def test_category_filter():
    """Test filtering by venue category."""
    print_header("TEST 4: Restaurant check-ins")

    result = await search_checkins_action({
        "category": "restaurant",
        "max_results": 5,
    })
    print(f"\n✓ {result['message']}")

    for checkin in result["checkins"]:
        venue = checkin["venue"]["name"]
        categories = checkin.get("categories", [])
        date = checkin["iso_time"][:10]
        print(f"  - {date}: {venue} ({', '.join(categories[:2])})")

    return True


async def test_combined_filters():
    """Test combining multiple filters."""
    print_header("TEST 5: Restaurant check-ins with companion in 2024")

    # Find a companion first
    recent = await search_checkins_action({
        "only_with_companions": True,
        "max_results": 5,
    })

    if not recent["checkins"]:
        print("\n⚠️  No check-ins with companions found")
        return True

    companion_name = recent["checkins"][0]["companions"][0]["first_name"]

    result = await search_checkins_action({
        "year": 2024,
        "with_companion": companion_name,
        "category": "restaurant",
        "max_results": 10,
    })
    print(f"\n✓ {result['message']}")
    print(f"  Searching for: restaurants with {companion_name} in 2024")

    if not result["checkins"]:
        print("  No matching check-ins found")
    else:
        for checkin in result["checkins"]:
            venue = checkin["venue"]["name"]
            categories = checkin.get("categories", [])
            date = checkin["iso_time"][:10]
            companions = [c["first_name"] for c in checkin.get("companions", [])]
            print(f"  - {date}: {venue}")
            print(f"    Categories: {', '.join(categories[:2])}")
            print(f"    With: {', '.join(companions)}")

    return True


async def test_only_with_companions():
    """Test filtering to only show check-ins with companions."""
    print_header("TEST 6: Only check-ins with companions")

    result = await search_checkins_action({
        "only_with_companions": True,
        "max_results": 5,
    })
    print(f"\n✓ {result['message']}")

    for checkin in result["checkins"]:
        venue = checkin["venue"]["name"]
        companions = [c["first_name"] for c in checkin.get("companions", [])]
        date = checkin["iso_time"][:10]
        print(f"  - {date}: {venue} (with {', '.join(companions)})")

    # Verify all have companions
    all_have_companions = all(
        len(c.get("companions", [])) > 0 for c in result["checkins"]
    )
    if all_have_companions:
        print("\n  ✓ All check-ins have companions")
    else:
        print("\n  ❌ Some check-ins are missing companions!")

    return all_have_companions


async def main():
    """Run all tests."""
    print("\n🧪 Testing Enhanced Swarm Check-ins API")
    print("=" * 60)

    await test_recent_checkins()
    await test_year_filter()
    await test_companion_filter()
    await test_category_filter()
    await test_combined_filters()
    await test_only_with_companions()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print("\nExample queries GPT can now answer:")
    print("  - 'What restaurant did Jimmy and I go to in 2024?'")
    print("  - 'Show my check-ins with Linda'")
    print("  - 'Where did I go with friends last month?'")
    print("  - 'List my coffee shop visits'\n")


if __name__ == "__main__":
    # Load .env file
    try:
        from dotenv import load_dotenv

        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            print(f"Loaded environment from {env_file}")
    except ImportError:
        print("python-dotenv not installed, relying on existing environment variables")

    asyncio.run(main())

