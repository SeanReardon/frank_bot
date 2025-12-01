#!/usr/bin/env python3
"""
Google API Credentials Setup Script

This script helps you authenticate with Google APIs and obtain credentials
for accessing Google Calendar and Contacts (People API).

Prerequisites:
1. Install required packages: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
2. Set up your .env file with GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes for Google Calendar and Contacts (People API)
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts'
]

def load_env():
    """Load environment variables from .env file using python-dotenv"""
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        print("Error: .env file not found. Please create it from .env.example")
        return False
    
    load_dotenv(env_path)
    return True

def create_credentials_json(client_id, client_secret, redirect_uri):
    """Create a credentials.json structure from environment variables"""
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
        }
    }

def get_credentials():
    """Get or refresh Google API credentials"""
    token_file = os.getenv('GOOGLE_TOKEN_FILE', 'token.json')
    creds = None
    
    # Check if we already have valid credentials
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If credentials don't exist or are invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds.refresh(Request())
        else:
            print("Starting OAuth flow...")
            print("A browser window will open for you to authorize the application.")
            
            # Create credentials JSON from env vars
            client_config = create_credentials_json(
                os.getenv('GOOGLE_CLIENT_ID'),
                os.getenv('GOOGLE_CLIENT_SECRET'),
                os.getenv('GOOGLE_REDIRECT_URI')
            )
            
            flow = InstalledAppFlow.from_client_config(
                client_config,
                SCOPES
            )
            creds = flow.run_local_server(port=8080)
        
        # Save credentials for future use
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
        print(f"Credentials saved to {token_file}")
    
    return creds

def test_apis(creds):
    """Test that we can access both Calendar and Contacts APIs"""
    print("\nTesting API access...")
    
    try:
        # Test Calendar API
        calendar_service = build('calendar', 'v3', credentials=creds)
        calendar_list = calendar_service.calendarList().list(maxResults=1).execute()
        print("✓ Successfully connected to Google Calendar API")
        
        # Test People API (Contacts)
        people_service = build('people', 'v1', credentials=creds)
        results = people_service.people().connections().list(
            resourceName='people/me',
            pageSize=1,
            personFields='names,emailAddresses'
        ).execute()
        print("✓ Successfully connected to Google People API (Contacts)")
        
        return True
    except Exception as e:
        print(f"✗ Error testing APIs: {e}")
        return False

def main():
    print("=== Google API Credentials Setup ===\n")
    
    # Load environment variables
    if not load_env():
        return
    
    # Check required variables
    required = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI']
    missing = []
    for var in required:
        value = os.getenv(var)
        if not value or value.startswith('your-'):
            missing.append(var)
    
    if missing:
        print("Error: Please set the following variables in your .env file:")
        for var in missing:
            print(f"  - {var}")
        print("\nTo get these credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project (or select existing)")
        print("3. Enable 'Google Calendar API' and 'People API'")
        print("4. Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'")
        print("5. Choose 'Desktop app' as application type")
        print("6. Download the JSON file and copy the values to your .env")
        return
    
    # Get or refresh credentials
    try:
        creds = get_credentials()
        print("\n✓ Authentication successful!")
        
        # Test API access
        test_apis(creds)
        
        print("\n=== Setup Complete ===")
        print("You can now use these credentials in your Python scripts.")
        print(f"Token saved in: {os.getenv('GOOGLE_TOKEN_FILE', 'token.json')}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nPlease verify your credentials in the .env file are correct.")

if __name__ == '__main__':
    main()
