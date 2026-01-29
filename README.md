# Frank Bot – OpenAI Actions Server

Frank Bot exposes Google Calendar and Google Contacts helpers over HTTPS via OpenAI Actions. Deploy it anywhere (Docker or bare metal), point OpenAI at `/.well-known/actions.json`, and the assistant can list events, create meetings, and search contacts.

## Quick Start

1. Set any desired environment variables (see below).
2. Build and run:

```bash
docker build -t frank-bot .
docker run \
  -e ACTIONS_API_KEY="super-secret" \
  -e PUBLIC_BASE_URL="https://example.com" \
  -p 8000:8000 \
  frank-bot
```

The HTTP API (and OpenAI manifest) will now be reachable at `https://example.com`.

## Development

This project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Run the server
poetry run python app.py

# Or activate the virtual environment and run directly
poetry shell
python app.py
```

### Alternative: pip install

If you prefer not to use Poetry:

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install from pyproject.toml
pip install .

# Run the server
python app.py
```

## Project Structure

```
frank_bot/
├── app.py                 # Server entrypoint (runs Starlette/uvicorn)
├── config.py              # Application settings from environment
├── logging_config.py      # Logging setup
│
├── server/                # HTTP transport layer
│   ├── app.py             # Starlette app factory
│   ├── routes.py          # Action route definitions
│   ├── manifests.py       # OpenAI manifest generation
│   └── openapi.py         # OpenAPI document loading
│
├── actions/               # Business logic (one file per domain)
│   ├── calendar.py        # Google Calendar actions
│   ├── contacts.py        # Google Contacts actions
│   ├── swarm.py           # Swarm/Foursquare actions
│   ├── system.py          # hello_world, time, server info
│   └── helpers.py         # Shared utilities
│
├── services/              # External API integrations
│   ├── google_calendar.py
│   ├── google_contacts.py
│   ├── ntp_time.py
│   └── swarm_service.py
│
├── openapi/               # OpenAPI specification
│   └── spec.json
│
├── tests/                 # Test suite
│   └── test_*.py
│
├── meta/                  # FrankAPI scripting module
│   ├── api.py             # FrankAPI class and namespaces
│   ├── scripts.py         # Script storage utilities
│   ├── jobs.py            # Job management
│   ├── executor.py        # Script execution
│   └── introspection.py   # API documentation generation
│
├── data/                  # Persistent data (Docker volume)
│   ├── scripts/           # Saved Python scripts
│   └── jobs/              # Job execution records
│
├── scripts/               # Dev/maintenance utilities
│   └── update_public_urls.py
│
├── docs/                  # Documentation
│   └── GOOGLE_API_SETUP.md
│
├── pyproject.toml         # Poetry dependencies
├── poetry.lock
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Available Tools

- `hello_world` - A simple hello world tool that greets the user
  - Optional parameter: `name` (string) - The name to greet (defaults to "World")
- `list_calendar_events` - List Google Calendar events for a day or time range
- `create_calendar_event` - Create a Google Calendar event with optional attendees
- `list_calendars` - Enumerate calendars accessible with the configured token
- `search_contacts` - Query Google Contacts via the People API
- `list_my_swarm_checkins` - Summarize your own latest Swarm check-ins (current location + recent history)
- `get_my_time` - Return the current local time and timezone for you (based on `DEFAULT_TIMEZONE`)
- `get_server_start` - Report when this container started and how long it has been running

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | HTTP bind address |
| `LOG_FILE` / `LOG_LEVEL` | `app.log` / `DEBUG` | Logging controls |
| `DEFAULT_TIMEZONE` | `America/Chicago` | Default timezone for day-based calendar queries |
| `GOOGLE_TOKEN_FILE` | `token.json` | OAuth token cache |
| `GOOGLE_CREDENTIALS_FILE` | _unset_ | Path to `credentials.json` |
| `GOOGLE_CALENDAR_SCOPES` | calendar scope | Comma-separated scopes |
| `GOOGLE_CONTACTS_SCOPES` | contacts scope | Comma-separated scopes |
| `ACTIONS_API_KEY` | _unset_ | Optional API key required via `X-API-Key` header |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Public URL used inside manifests & OpenAPI |
| `ACTIONS_NAME_FOR_HUMAN` | `Frank Bot` | Manifest/OpenAPI metadata |
| `ACTIONS_NAME_FOR_MODEL` | `frank_bot` | Manifest/OpenAPI metadata |
| `ACTIONS_DESCRIPTION_FOR_HUMAN` | _see code_ | Human description |
| `ACTIONS_DESCRIPTION_FOR_MODEL` | _see code_ | Model-facing description |
| `ACTIONS_LOGO_URL` | _unset_ | Optional logo URL for manifests |
| `ACTIONS_CONTACT_EMAIL` | _unset_ | Manifest contact email |
| `ACTIONS_LEGAL_URL` | _unset_ | Terms/Privacy URL in manifest |
| `ACTIONS_OPENAPI_PATH` | `openapi/spec.json` | Path to the OpenAPI document |
| `SWARM_OAUTH_TOKEN` | _unset_ | OAuth token for Swarm/Foursquare API access |
| `SWARM_API_VERSION` | `20240501` | API version parameter passed to Swarm endpoints |
| `APP_VERSION` | `0.5.0` | Version string used in metadata |

## Registering with OpenAI Actions

1. Deploy the server somewhere HTTPS-accessible (`PUBLIC_BASE_URL` should match the public origin).
2. Verify these URLs load in a browser:
   - `https://<your-domain>/.well-known/actions.json`
   - `https://<your-domain>/actions/openapi.json`
3. In ChatGPT (Settings → Actions → *Create*) or the Assistants dashboard, choose **Import from URL** and provide `https://<your-domain>/.well-known/actions.json`.
4. When prompted for auth, pick **Custom** and set header `X-API-Key` to the same value you stored in `ACTIONS_API_KEY`.
5. Save the Action and test it with a natural language request (e.g., "List my meetings today").

## OpenAI Actions API

Frank Bot exposes these HTTP routes once the server is reachable from the public internet:

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/actions/hello` | Diagnostic greeting |
| `GET` | `/actions/calendar/events` | List events via query params |
| `GET` | `/actions/calendar/schedule` | Create a calendar event |
| `GET` | `/actions/calendar/calendars` | List calendars |
| `GET` | `/actions/contacts/search` | Search Google Contacts |
| `GET` | `/actions/swarm/self` | Latest check-ins for your own Swarm account |
| `GET` | `/actions/me/time` | Current time and timezone for you |
| `GET` | `/actions/server/version` | Docker start timestamp and uptime |

Helpful discovery endpoints:

- `GET /actions/openapi.json` – generated OpenAPI 3.1 document
- `GET /.well-known/ai-plugin.json` – ChatGPT plugin style manifest
- `GET /.well-known/actions.json` – lightweight manifest for Assistants
- `GET /health` – health probe

When `ACTIONS_API_KEY` is set, every Actions route expects `X-API-Key: <value>`. Leave it unset for local testing, but always enable it (or place the server behind another auth layer) before exposing the service publicly.

### Swarm integration

Set `SWARM_OAUTH_TOKEN` (and optionally `SWARM_API_VERSION`) to enable the Swarm-powered action `list_my_swarm_checkins`, which returns your current Swarm location plus the most recent venues you've visited. Tokens come from https://developer.foursquare.com/ after authorizing the Swarm app; if the token is missing the endpoint will return a descriptive error. The `get_my_time` action uses `DEFAULT_TIMEZONE`, so set that env var to your home location (default `America/Chicago`).

### Telegram integration

Frank Bot can send and receive Telegram messages using your personal Telegram account (not a bot). This allows messaging to any Telegram user, group, or channel you have access to.

**Setup steps:**

1. **Get API credentials** from https://my.telegram.org:
   - Log in with your phone number
   - Go to "API development tools"
   - Create an application to get your `api_id` and `api_hash`

2. **Set environment variables** in your `.env` file:
   ```
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   TELEGRAM_PHONE=+15551234567
   TELEGRAM_SESSION_NAME=frank_bot  # optional, default: frank_bot
   ```

3. **Run the setup script** to authenticate:
   ```bash
   poetry run python scripts/setup_telegram_session.py
   ```
   This will:
   - Send a verification code to your Telegram app
   - Prompt you to enter the code
   - Handle 2FA if enabled
   - Create a `.session` file for persistent authentication

4. **Keep the session file secure** - it provides access to your Telegram account without needing the verification code again. The `.session` file should be in your `.gitignore`.

**Available endpoints:**
- `GET /actions/telegram/send?recipient=@username&text=Hello` - Send a message
- `GET /actions/telegram/messages?chat=@username&limit=20` - Get messages from a chat
- `GET /actions/telegram/chats?limit=20` - List recent conversations

**Note:** Unlike SMS, Telegram messages are sent from YOUR personal account. Recipients will see messages coming from you, not from a service number.

## Maintaining the OpenAPI document

The canonical specification lives at `openapi/spec.json`. Update that file whenever you change the HTTP surface, then restart the server (or redeploy) so the new document is served at `/actions/openapi.json`. A quick workflow:

```bash
# Validate formatting
python -m json.tool openapi/spec.json > /tmp/openapi.pretty.json && mv /tmp/openapi.pretty.json openapi/spec.json

# Optional: lint with speccy / openapi-cli if installed
npx @redocly/cli lint openapi/spec.json

# Update public URLs in static files (uses PUBLIC_BASE_URL)
python scripts/update_public_urls.py
```

## CI/CD

The project includes a GitHub Actions workflow (`.github/workflows/build_and_push.yml`) that:

- Builds Docker images on push to `main` and on version tags (`v*`)
- Pushes to GitHub Container Registry (`ghcr.io/seanreardon/frank_bot`)
- Supports multi-architecture builds (amd64, arm64)
- Uses GitHub Actions cache for faster builds

To pull the latest image:

```bash
docker pull ghcr.io/seanreardon/frank_bot:latest
```

## Data Directory

The `./data` directory is mounted as a volume to persist scripts and job records:

```
data/
├── scripts/    # Saved Python scripts (*.py)
│               # Filename format: {ISO8601-timestamp}-{slug}.py
│               # Example: 2024-01-15T10-30-00Z-find-hotels.py
│
└── jobs/       # Job execution records (*.json)
                # Filename format: {ISO8601-timestamp}-{slug}-run.json
                # Contains: job_id, script_id, status, params, stdout, stderr, result, error
```

Scripts are executed via the `/frank/execute` endpoint and can be reused by referencing their `script_id`. Job records track execution status (pending, running, completed, failed, timeout) and capture output for later retrieval via `/frank/jobs/{id}`.
