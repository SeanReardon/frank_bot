# Google API Setup Guide

This guide walks you through setting up Google OAuth credentials for Frank Bot to access Google Calendar and Google Contacts.

## Prerequisites

1. A Google Cloud Platform account
2. A Google Cloud project (create one at https://console.cloud.google.com/)

## Step 1: Enable APIs

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **APIs & Services** > **Library**
4. Enable these APIs:
   - Google Calendar API
   - People API (for Contacts)

## Step 2: Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Choose **External** user type (unless you have a Google Workspace account)
3. Fill in the required fields:
   - App name: `Frank Bot`
   - User support email: Your email
   - Developer contact: Your email
4. Add scopes:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/contacts`
5. Add your email as a test user

## Step 3: Create OAuth Credentials

1. Navigate to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. Choose **Desktop app** as the application type
4. Name it `Frank Bot Desktop`
5. Download the JSON file
6. Save it as `google-credentials.json` in the project root

## Step 4: Generate Token

Run the setup script to generate your OAuth token:

```bash
python setup_google_credentials.py
```

This will:
1. Open a browser window for Google authentication
2. Ask you to grant permissions
3. Save the token to `token.json`

## Environment Variables

Set these in your `.env` file:

```bash
GOOGLE_TOKEN_FILE=token.json
GOOGLE_CREDENTIALS_FILE=google-credentials.json
GOOGLE_CALENDAR_SCOPES=https://www.googleapis.com/auth/calendar
GOOGLE_CONTACTS_SCOPES=https://www.googleapis.com/auth/contacts
```

## Troubleshooting

### "Access blocked: This app's request is invalid"

This usually means the OAuth consent screen isn't properly configured. Make sure:
- Your email is added as a test user
- The required scopes are added

### "Token has been expired or revoked"

Delete `token.json` and run `setup_google_credentials.py` again to refresh.

### "File not found: token.json"

Run the setup script first:
```bash
python setup_google_credentials.py
```

