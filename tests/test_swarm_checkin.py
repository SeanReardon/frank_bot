#!/usr/bin/env python3
"""
Test script to fetch the most recent Swarm check-in.
"""

import sys
from pathlib import Path

# Add the project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.swarm_service import SwarmService, describe_checkin


def test_recent_checkin():
    """Fetch and display the most recent check-in."""
    print("Fetching most recent Swarm check-in...")
    print("-" * 50)

    try:
        service = SwarmService()
        checkins = service.get_self_checkins(limit=1)

        if not checkins:
            print("❌ No check-ins found")
            return False

        print(f"✓ Found {len(checkins)} check-in(s)\n")

        # Describe the most recent one
        most_recent = describe_checkin(checkins[0])

        print("Most Recent Check-in:")
        print(f"  Venue: {most_recent.get('venue_name')}")
        print(f"  Address: {most_recent.get('city')}, {most_recent.get('state')} {most_recent.get('country')}")
        print(f"  Coordinates: ({most_recent.get('latitude')}, {most_recent.get('longitude')})")
        print(f"  Time: {most_recent.get('iso_time')}")
        if most_recent.get('minutes_since') is not None:
            mins = most_recent.get('minutes_since')
            if mins < 60:
                print(f"  ({mins} minutes ago)")
            elif mins < 1440:
                print(f"  ({mins // 60} hours ago)")
            else:
                print(f"  ({mins // 1440} days ago)")
        if most_recent.get('shout'):
            print(f"  Comment: {most_recent.get('shout')}")
        if most_recent.get('categories'):
            print(f"  Categories: {', '.join(most_recent.get('categories'))}")
        if most_recent.get('canonical_url'):
            print(f"  URL: {most_recent.get('canonical_url')}")

        print("\n" + "=" * 50)
        print("✅ Successfully retrieved check-in data!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    # Load .env file
    try:
        from dotenv import load_dotenv
        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            print(f"Loaded environment from {env_file}\n")
    except ImportError:
        print("python-dotenv not installed\n")

    success = test_recent_checkin()
    sys.exit(0 if success else 1)

