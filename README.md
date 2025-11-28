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

To run locally without Docker:

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
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
| `ACTIONS_OPENAPI_PATH` | `actions/openapi.json` | Path to the OpenAPI document served at `/actions/openapi.json` |
| `SWARM_OAUTH_TOKEN` | _unset_ | OAuth token for Swarm/Foursquare API access |
| `SWARM_API_VERSION` | `20240501` | API version parameter passed to Swarm endpoints |
| `APP_VERSION` | `0.3.0` | Version string used in metadata |

## Registering with OpenAI Actions

1. Deploy the server somewhere HTTPS-accessible (`PUBLIC_BASE_URL` should match the public origin).
2. Verify these URLs load in a browser:
   - `https://<your-domain>/.well-known/actions.json`
   - `https://<your-domain>/actions/openapi.json`
3. In ChatGPT (Settings → Actions → *Create*) or the Assistants dashboard, choose **Import from URL** and provide `https://<your-domain>/.well-known/actions.json`.
4. When prompted for auth, pick **Custom** and set header `X-API-Key` to the same value you stored in `ACTIONS_API_KEY`.
5. Save the Action and test it with a natural language request (e.g., “List my meetings today”).

## OpenAI Actions API

Frank Bot exposes these HTTP routes once the server is reachable from the public internet:

| Method | Path | Description |
| --- | --- | --- |
| `GET/POST` | `/actions/hello` | Diagnostic greeting |
| `GET` | `/actions/calendar/events` | List events via query params |
| `POST` | `/actions/calendar/events:list` | List events via JSON payload |
| `POST` | `/actions/calendar/events:create` | Create a calendar event |
| `GET` | `/actions/calendar/calendars` | List calendars via query params |
| `POST` | `/actions/calendar/calendars:list` | List calendars via JSON |
| `GET/POST` | `/actions/contacts/search` | Search Google Contacts |
| `GET/POST` | `/actions/swarm/self` | Latest check-ins for your own Swarm account |
| `GET/POST` | `/actions/me/time` | Current time and timezone for you |
| `GET/POST` | `/actions/server/version` | Docker start timestamp and uptime |

Helpful discovery endpoints:

- `GET /actions/openapi.json` – generated OpenAPI 3.1 document
- `GET /.well-known/ai-plugin.json` – ChatGPT plugin style manifest
- `GET /.well-known/actions.json` – lightweight manifest for Assistants
- `GET /health` – health probe

When `ACTIONS_API_KEY` is set, every Actions route expects `X-API-Key: <value>`. Leave it unset for local testing, but always enable it (or place the server behind another auth layer) before exposing the service publicly.

### Swarm integration

Set `SWARM_OAUTH_TOKEN` (and optionally `SWARM_API_VERSION`) to enable the Swarm-powered action `list_my_swarm_checkins`, which returns your current Swarm location plus the most recent venues you've visited. Tokens come from https://developer.foursquare.com/ after authorizing the Swarm app; if the token is missing the endpoint will return a descriptive error. The `get_my_time` action uses `DEFAULT_TIMEZONE`, so set that env var to your home location (default `America/Chicago`).

## Maintaining the OpenAPI document

The canonical specification lives at `actions/openapi.json`. Update that file whenever you change the HTTP surface, then restart the server (or redeploy) so the new document is served at `/actions/openapi.json`. A quick workflow:

```bash
# Validate formatting
python -m json.tool actions/openapi.json > /tmp/openapi.pretty.json && mv /tmp/openapi.pretty.json actions/openapi.json

# Optional: lint with speccy / openapi-cli if installed
npx @redocly/cli lint actions/openapi.json
```

If you prefer to regenerate the file from the current server, call `GET /actions/openapi.json` and overwrite `actions/openapi.json` with the response (or copy it straight from the repo before making changes). Once the spec is updated, tools like OpenAI Actions, Postman, or `openapi-python-client` can ingest it directly with no additional wiring.

### Python client SDK & base URL updates

A typed client lives in `clients/frank_bot_client`, generated with [`openapi-python-client`](https://github.com/openapi-generators/openapi-python-client). Regenerate it whenever the spec changes:

```bash
source venv/bin/activate
openapi-python-client generate \
  --path actions/openapi.json \
  --config openapi-python-client.json \
  --output-path clients \
  --overwrite

# Update public URLs in static files (uses PUBLIC_BASE_URL)
python scripts/update_public_urls.py
```

The config in `openapi-python-client.json` keeps the package name/version aligned with the server. After regeneration you can install the client into other projects via `pip install ./clients/frank_bot_client` or by following the instructions inside `clients/README.md`.

## Project Structure

```
frank_bot/
├── app.py              # Server entrypoint (runs Starlette/uvicorn)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container build
├── .env.example        # Environment variable template
└── README.md           # This file
```

