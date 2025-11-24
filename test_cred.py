#!/usr/bin/env python3
"""
Test script to verify Google Calendar and Contacts API access
"""

import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts'
]

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

def load_credentials():
    """Load credentials from .env and token file, or create new ones"""
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    
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
            print("No valid credentials found. Starting OAuth flow...")
            print("A browser window will open for authorization.\n")
            
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
        print(f"Credentials saved to {token_file}\n")
    
    return creds

def test_contacts(creds):
    """Fetch and display 10 contacts"""
    print("\n=== CONTACTS ===\n")
    
    service = build('people', 'v1', credentials=creds)
    
    results = service.people().connections().list(
        resourceName='people/me',
        pageSize=10,
        personFields='names,emailAddresses,phoneNumbers'
    ).execute()
    
    connections = results.get('connections', [])
    
    if not connections:
        print("No contacts found.")
        return
    
    for i, person in enumerate(connections, 1):
        names = person.get('names', [])
        emails = person.get('emailAddresses', [])
        phones = person.get('phoneNumbers', [])
        
        if names:
            name = names[0].get('displayName', 'No name')
            print(f"{i}. {name}")
            
            if emails:
                for email in emails:
                    print(f"   Email: {email.get('value', '')}")
            
            if phones:
                for phone in phones:
                    print(f"   Phone: {phone.get('value', '')}")
            print()

def test_calendar(creds):
    """Fetch and display upcoming calendar events"""
    print("\n=== CALENDAR EVENTS ===\n")
    
    service = build('calendar', 'v3', credentials=creds)
    
    now = datetime.utcnow().isoformat() + 'Z'
    
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    if not events:
        print("No upcoming events found.")
        return
    
    for i, event in enumerate(events, 1):
        start = event['start'].get('dateTime', event['start'].get('date'))
        summary = event.get('summary', 'No title')
        
        # Parse and format the date
        try:
            if 'T' in start:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                formatted = dt.strftime('%Y-%m-%d %H:%M')
            else:
                formatted = start
        except:
            formatted = start
        
        print(f"{i}. {formatted} - {summary}")
        
        if event.get('description'):
            desc = event['description'][:100]
            print(f"   {desc}{'...' if len(event['description']) > 100 else ''}")
        print()

def main():
    print("=== Testing Google API Credentials ===")
    
    creds = load_credentials()
    if not creds:
        return
    
    try:
        test_contacts(creds)
        test_calendar(creds)
        print("\n✓ Successfully accessed both APIs!")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure you've run setup_google_credentials.py first.")

if __name__ == '__main__':
    main()
