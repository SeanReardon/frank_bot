#!/usr/bin/env python3
"""
Test script to verify Swarm/Foursquare OAuth credentials are configured correctly.
"""

import os
import sys
from pathlib import Path

# Add the project root to sys.path so we can import frank_bot modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from frank_bot.services.swarm_service import SwarmService, SwarmAPIError


def test_swarm_credentials():
    """Test that Swarm OAuth token works by fetching basic user data."""
    print("Testing Swarm API credentials...")
    print("-" * 50)
    
    # Check that the env var is set
    oauth_token = os.getenv("SWARM_OAUTH_TOKEN")
    if not oauth_token:
        print("❌ SWARM_OAUTH_TOKEN environment variable is not set")
        print("   Please set it in your .env file")
        return False
    
    print(f"✓ SWARM_OAUTH_TOKEN is set (length: {len(oauth_token)})")
    
    # Try to initialize the service
    try:
        service = SwarmService()
        print("✓ SwarmService initialized successfully")
    except ValueError as e:
        print(f"❌ Failed to initialize SwarmService: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error initializing SwarmService: {e}")
        return False
    
    # Try to fetch friends list
    try:
        print("\nFetching friends list...")
        friends = service.get_friends()
        print(f"✓ Successfully retrieved {len(friends)} friends")
        if friends:
            print("\nFirst few friends:")
            for friend in friends[:5]:
                print(f"  - {friend.display_name} (ID: {friend.id})")
    except SwarmAPIError as e:
        print(f"❌ Swarm API error when fetching friends: {e}")
        print("\nThis likely means:")
        print("  - Your SWARM_OAUTH_TOKEN is invalid or expired")
        print("  - You don't have permission to access this data")
        return False
    except Exception as e:
        print(f"❌ Unexpected error fetching friends: {e}")
        return False
    
    # Try to fetch recent checkins
    try:
        print("\nFetching recent checkins...")
        checkins = service.get_self_checkins(limit=5)
        print(f"✓ Successfully retrieved {len(checkins)} recent checkins")
        if checkins:
            print("\nMost recent checkin:")
            from frank_bot.services.swarm_service import describe_checkin
            most_recent = describe_checkin(checkins[0])
            print(f"  Venue: {most_recent.get('venue_name')}")
            print(f"  Location: {most_recent.get('city')}, {most_recent.get('state')}")
            print(f"  Time: {most_recent.get('iso_time')}")
            if most_recent.get('minutes_since') is not None:
                print(f"  ({most_recent.get('minutes_since')} minutes ago)")
    except SwarmAPIError as e:
        print(f"❌ Swarm API error when fetching checkins: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error fetching checkins: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ All Swarm API credential tests passed!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    # Load .env file if it exists
    try:
        from dotenv import load_dotenv
        env_file = project_root / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            print(f"Loaded environment from {env_file}\n")
    except ImportError:
        print("python-dotenv not installed, relying on existing environment variables\n")
    
    success = test_swarm_credentials()
    sys.exit(0 if success else 1)
