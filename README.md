# Frank Bot – OpenAI Actions Server

Frank Bot exposes Google Calendar and Google Contacts helpers over HTTPS via OpenAI Actions. Deploy it anywhere (Docker or bare metal), point OpenAI at `/.well-known/actions.json`, and the assistant can list events, create meetings, and search contacts.

## Quick Start

1. Set any desired environment variables (see below).
2. Build and run:

```bash
docker build -t frank-bot .
docker run \
  -e VAULT_ADDR="http://concordia-vault:8200" \
  -e VAULT_ROLE_ID="your-role-id" \
  -e VAULT_SECRET_ID="your-secret-id" \
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
| `VAULT_ADDR` | _unset_ | Vault address (Concordia) |
| `VAULT_ROLE_ID` | _unset_ | Vault AppRole role_id |
| `VAULT_SECRET_ID` | _unset_ | Vault AppRole secret_id |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | HTTP bind address |
| `LOG_FILE` / `LOG_LEVEL` | `app.log` / `DEBUG` | Logging controls |
| `DEFAULT_TIMEZONE` | `America/Chicago` | Default timezone for day-based calendar queries |
| `GOOGLE_TOKEN_FILE` | `token.json` | OAuth token cache |
| `GOOGLE_CREDENTIALS_FILE` | _unset_ | Path to `credentials.json` |
| `GOOGLE_CALENDAR_SCOPES` | calendar scope | Comma-separated scopes |
| `GOOGLE_CONTACTS_SCOPES` | contacts scope | Comma-separated scopes |
| `ACTIONS_API_KEY` | _unset_ | Dev fallback only (use Vault: `secret/frank-bot/actions`) |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Public URL used inside manifests & OpenAPI |
| `ACTIONS_NAME_FOR_HUMAN` | `Frank Bot` | Manifest/OpenAPI metadata |
| `ACTIONS_NAME_FOR_MODEL` | `frank_bot` | Manifest/OpenAPI metadata |
| `ACTIONS_DESCRIPTION_FOR_HUMAN` | _see code_ | Human description |
| `ACTIONS_DESCRIPTION_FOR_MODEL` | _see code_ | Model-facing description |
| `ACTIONS_LOGO_URL` | _unset_ | Optional logo URL for manifests |
| `ACTIONS_CONTACT_EMAIL` | _unset_ | Manifest contact email |
| `ACTIONS_LEGAL_URL` | _unset_ | Terms/Privacy URL in manifest |
| `ACTIONS_OPENAPI_PATH` | `openapi/spec.json` | Path to the OpenAPI document |
| `SWARM_OAUTH_TOKEN` | _unset_ | Dev fallback only (use Vault: `secret/frank-bot/swarm`) |
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

When the Actions API key is configured (Vault: `secret/frank-bot/actions`), every Actions route expects `X-API-Key: <value>`. For local/dev runs without Vault, you can set `ACTIONS_API_KEY` as an environment variable fallback.

### Swarm integration

Configure Swarm/Foursquare credentials in Vault at `secret/frank-bot/swarm` (keys: `oauth_token`, `api_key`). For local/dev runs without Vault, `SWARM_OAUTH_TOKEN` (and optionally `SWARM_API_VERSION`) can be used as a fallback.

### Telegram integration

Frank Bot can send and receive Telegram messages using your personal Telegram account (not a bot). This allows messaging to any Telegram user, group, or channel you have access to.

**Setup steps:**

1. **Get API credentials** from https://my.telegram.org:
   - Log in with your phone number
   - Go to "API development tools"
   - Create an application to get your `api_id` and `api_hash`

2. **Store API credentials in Vault** at `secret/frank-bot/telegram` (keys: `api_id`, `api_hash`, `phone`).
   - The service reads them via `services/vault_client.py` (AppRole)
   - `TELEGRAM_SESSION_NAME` is non-secret and can remain default (`frank_bot`) or be set via env if needed

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

### Jorbs (Autonomous Tasks)

Jorbs are long-lived autonomous tasks that Frank Bot can execute on your behalf. They can send messages via SMS, Telegram, or email, and coordinate multi-step interactions with businesses, services, or other parties.

**Key features:**
- LLM-powered decision making (uses gpt-5.2 model)
- Automatic message debouncing (batches rapid messages together)
- Policy enforcement (spending limits, approval requirements)
- Context reset mechanism ("Ralph Loop") for long-running tasks
- Daily digest emails summarizing activity

**Environment variables:**

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | _unset_ | Dev fallback only (Vault: `secret/frank-bot/openai`) |
| `JORBS_DB_PATH` | `./data/jorbs.db` | SQLite database for jorb storage |
| `JORBS_PROGRESS_LOG` | `./data/jorbs_progress.txt` | Progress log for context resets |
| `AGENT_SPEND_LIMIT` | `100.0` | Max spending (USD) before requiring approval |
| `CONTEXT_RESET_DAYS` | `3` | Days before context is reset |
| `DEBOUNCE_TELEGRAM_SECONDS` | `60` | Telegram message debounce window |
| `DEBOUNCE_SMS_SECONDS` | `30` | SMS message debounce window |
| `SMTP_HOST` | _unset_ | Dev fallback only (Vault: `secret/frank-bot/email`) |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | _unset_ | Dev fallback only (Vault: `secret/frank-bot/email`) |
| `SMTP_PASSWORD` | _unset_ | Dev fallback only (Vault: `secret/frank-bot/email`) |
| `DIGEST_EMAIL_TO` | _unset_ | Dev fallback only (Vault: `secret/frank-bot/email`) |
| `DIGEST_TIME` | `08:00` | Dev fallback only (Vault: `secret/frank-bot/email`) |

**Available endpoints:**
- `GET /jorbs` - List all jorbs
- `GET /jorbs/create` - Create a new jorb
- `GET /jorbs/{id}` - Get jorb details
- `GET /jorbs/{id}/messages` - Get jorb message history
- `GET /jorbs/{id}/approve` - Approve a paused jorb
- `GET /jorbs/{id}/cancel` - Cancel a jorb
- `GET /jorbs/brief` - Get activity briefing

### Android Phone Automation

Frank Bot can control a dedicated Android phone via ADB, enabling LLM-in-the-loop automation for apps like Google Home (thermostat control), Uber, DoorDash, and more.

ADB transport options:
- **USB (preferred)**: stable, works even if the phone has Wi‑Fi/cellular disabled
- **TCP/IP (wireless debugging)**: convenient, but depends on network reachability

**Device Requirements:**
- Android 10+
- ADB authorized for the host running frank_bot (ADB keys are persisted via `./adb-keys:/root/.android`)
- If using USB: USB passthrough to the container (`/dev/bus/usb` is mounted in `docker-compose.yml`)
- If using TCP/IP: phone reachable from the container network

**Setup steps:**

1. **USB (recommended / onlogic-closet default)**:
   - Plug the phone into the host and confirm it appears in `adb devices`
   - Set the device serial (example: `48151FDKD001UD`) in Vault at `secret/frank-bot/android` (`device_serial`)
     - On container start, `scripts/entrypoint.sh` will export `ANDROID_DEVICE_SERIAL` from Vault settings (if unset)
   - If the phone has Wi‑Fi/cellular off, `gnirehtet` will automatically start (when `ANDROID_DEVICE_SERIAL` is set) to provide USB internet

2. **TCP/IP (wireless debugging fallback)**:
   - Enable wireless debugging on the phone (Settings → Developer Options → Wireless debugging)
   - Pair from the host: `adb pair <ip>:<pairing-port>`
   - Set Vault `adb_host`/`adb_port` (or env vars `ANDROID_ADB_HOST`/`ANDROID_ADB_PORT`)

3. **For LLM-in-the-loop automation**, also configure:
   ```
   ANDROID_LLM_MODEL=gpt-5.2     # Vision-capable model
   ANDROID_LLM_API_KEY=sk-...    # Dev fallback only (prefer Vault); uses OpenAI key if unset
   ```

**Environment variables:**

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANDROID_DEVICE_SERIAL` | _unset_ | **USB ADB** serial (preferred). Example: `48151FDKD001UD` |
| `ANDROID_ADB_HOST` | _unset_ | **TCP/IP ADB** host (fallback). Set explicitly (no baked-in default). |
| `ANDROID_ADB_PORT` | `5555` | **TCP/IP ADB** port (fallback) |
| `ANDROID_LLM_MODEL` | `gpt-5.2` | Vision-capable LLM for automation |
| `ANDROID_LLM_API_KEY` | _unset_ | Dev fallback only (prefer Vault; falls back to OpenAI key) |
| `ANDROID_MAINTENANCE_CRON` | `0 3 1 * *` | Monthly maintenance schedule |
| `ANDROID_HEALTH_CHECK_CRON` | `0 4 * * 0` | Weekly health check schedule |

**Available endpoints:**
- `GET /actions/androidPhone/getScreen` - Capture screen state (screenshot + UI XML)
- `GET /actions/androidPhone/health` - Device health check (no API key required)
- `GET /actions/android/status` - Connection status
- `GET /actions/android/tap?x=540&y=1200` - Tap at coordinates
- `GET /actions/android/swipe?direction=up` - Swipe gesture
- `GET /actions/android/type?text=hello` - Type text
- `GET /actions/android/launch?app=chrome` - Launch app
- `GET /actions/android/key?key=home` - Press key (home, back, etc.)

**Supported apps** (common names mapped to packages):
chrome, settings, maps, youtube, uber, lyft, doordash, ubereats, grubhub, instacart, whatsapp, instagram, telegram, venmo, cashapp, and more.

**Cost considerations:**
LLM-in-the-loop operations (like thermostat control) use vision-capable models which consume more tokens. Each screen capture + decision typically costs $0.01-0.05 depending on the model. Complex tasks may require multiple steps.

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

Scripts are executed via `POST /frank/script/task/start` and can be reused by referencing their `script_id`. Job records track execution status (pending, running, completed, failed, timeout) and capture output for retrieval via `GET /frank/script/task/status?task_id=...`.
