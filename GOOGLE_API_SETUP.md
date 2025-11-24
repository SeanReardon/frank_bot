# Google API Setup Guide

This guide will help you set up Google Calendar and Contacts API access for your Python scripts.

## Step 1: Install Required Packages

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

## Step 2: Create Google Cloud Project and Get Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the required APIs:
   - Go to "APIs & Services" > "Library"
   - Search for and enable **"Google Calendar API"**
   - Search for and enable **"People API"** (for Contacts)

4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - If prompted, configure the OAuth consent screen:
     - Choose "External" (unless you have a Google Workspace)
     - Fill in the app name and your email
     - Add your email as a test user
     - Save and continue through the steps
   - Back at "Create OAuth client ID":
     - Choose **"Desktop app"** as the application type
     - Give it a name (e.g., "Frank Bot Desktop")
     - Click "Create"

5. Download the credentials:
   - You'll see a popup with your client ID and client secret
   - **Copy these values** - you'll need them for the next step

## Step 3: Configure Your .env File

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and fill in the Google credentials you just created:
   ```bash
   GOOGLE_CLIENT_ID=your-actual-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-actual-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:8080/
   GOOGLE_TOKEN_FILE=token.json
   ```

## Step 4: Run the Setup Script

This will open a browser window for you to authorize the application:

```bash
python3 setup_google_credentials.py
```

Follow the prompts:
1. A browser window will open
2. Sign in with your Google account
3. Review the permissions (Calendar and Contacts access)
4. Click "Allow"
5. The script will save your credentials to `token.json`

**Note:** You may see a warning that the app is not verified. This is normal for personal projects. Click "Advanced" > "Go to [App Name] (unsafe)" to proceed.

## Step 5: Test the Setup

Run the example script to verify everything works:

```bash
python3 google_api_example.py
```

This will list your upcoming calendar events and contacts.

## Using in Your Own Scripts

Here's a minimal example to get you started:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/contacts'
]

# Load credentials
creds = Credentials.from_authorized_user_file('token.json', SCOPES)

# Use Calendar API
calendar = build('calendar', 'v3', credentials=creds)
events = calendar.events().list(calendarId='primary', maxResults=10).execute()

# Use People API (Contacts)
people = build('people', 'v1', credentials=creds)
contacts = people.people().connections().list(
    resourceName='people/me',
    pageSize=10,
    personFields='names,emailAddresses'
).execute()
```

## Files Created

- `.env` - Your credentials (DO NOT commit to git)
- `token.json` - OAuth token (DO NOT commit to git)
- `.env.example` - Template for credentials (safe to commit)

## Security Notes

1. **Never commit `.env` or `token.json` to version control**
2. Add them to your `.gitignore`:
   ```
   .env
   token.json
   ```
3. The token file will automatically refresh when it expires
4. If you need to revoke access, go to [Google Account Permissions](https://myaccount.google.com/permissions)

## Troubleshooting

### "Access blocked: Authorization Error"
- Make sure you've added yourself as a test user in the OAuth consent screen
- Check that both APIs are enabled in your Google Cloud project

### "Token has been expired or revoked"
- Delete `token.json` and run `setup_google_credentials.py` again

### "The user has not granted the app..."
- Make sure you clicked "Allow" for both Calendar and Contacts permissions
- Try deleting `token.json` and authorizing again

## API Documentation

- [Google Calendar API](https://developers.google.com/calendar/api/v3/reference)
- [Google People API (Contacts)](https://developers.google.com/people/api/rest/v1/people)
