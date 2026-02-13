# CLAUDE.md

This file provides context for AI assistants working on this codebase.

## Project Overview

Frank Bot is a personal OpenAI Actions server that exposes Google Calendar, Google Contacts, Swarm/Foursquare location data, SMS messaging, and system diagnostics over HTTPS. It's designed for integration with ChatGPT and other AI assistants.

## Architecture

```
actions/     → Business logic (one file per domain)
services/    → External API wrappers (Google, Swarm, Telnyx, NTP)
server/      → HTTP transport layer (Starlette routes, manifests, OpenAPI)
openapi/     → OpenAPI 3.1 specification (spec.json)
tests/       → pytest test suite
```

## Key Patterns

**Action handlers** follow this signature:
```python
async def action_name(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
```

**Routes** use GET methods exclusively (minimizes ChatGPT confirmation prompts) with query parameters as action arguments.

**Services** are classes wrapping external APIs (GoogleCalendarService, SwarmService, etc.).

**Helpers** in `actions/helpers.py` provide type coercion, timezone handling, datetime formatting, and fuzzy name matching.

## Development

```bash
# Install dependencies
poetry install

# Run server
poetry run python app.py

# Run tests
pytest tests/

# Lint OpenAPI spec
npx @redocly/cli lint openapi/spec.json
```

## Adding a New Action

1. Create or update a file in `actions/` with the async handler function
2. Add the route in `server/routes.py` using the `_build_responder()` wrapper
3. Update `openapi/spec.json` with the new endpoint specification
4. Add tests in `tests/`

## Environment Variables

**Vault-first:** Secrets live in Concordia Vault under `secret/frank-bot/*`,
managed by this repo’s `terraform/vault/`.

**Minimal `.env`:** only the Vault AppRole connection info:
- `VAULT_ADDR`
- `VAULT_ROLE_ID`
- `VAULT_SECRET_ID`

Non-secret config commonly set via environment / compose:
- `PUBLIC_BASE_URL` - Public URL for manifests/OpenAPI servers
- `GOOGLE_TOKEN_FILE` / `GOOGLE_CREDENTIALS_FILE` - Google OAuth files (state/files, not Vault)

Dev-only fallbacks (avoid in prod; prefer Vault):
- `ACTIONS_API_KEY`, `OPENAI_API_KEY`, `SWARM_OAUTH_TOKEN`, `TELNYX_*`, `TELEGRAM_*`, `SMTP_*`

## What NOT to Modify

- `token.json` - OAuth token cache (auto-generated)
- `.env` files - User-specific configuration
- `credentials.json` - User's Google OAuth credentials

## Deploy Auth Responsibilities

- Deployment auth is infra-owned in `homelab-infra` and read at runtime from Vault.
- Canonical deploy-auth path for this repo: `secret/homelab/deploy-auth/frank_bot`.
- The deploy PAT from that path is used for both HTTPS git fetch and GHCR image pulls.
- This repo continues to own only its application secret schema/policies in Vault.
- Do not rely on persistent deployment creds in `~/.docker/config.json` or `~/.git-credentials`.

