# Rollback Procedure

How to revert frank-bot to a previous version when a deploy breaks production.

## Quick Rollback (revert to previous image)

On the production host:

```bash
# 1. Pull and run a specific known-good commit
export GOOD_SHA="<commit-sha>"
docker compose down
docker pull "ghcr.io/seanreardon/frank_bot:${GOOD_SHA}"
docker tag "ghcr.io/seanreardon/frank_bot:${GOOD_SHA}" ghcr.io/seanreardon/frank_bot:latest
docker compose up -d

# 2. Verify recovery
./scripts/smoke_test.sh
```

If the image isn't tagged by SHA, roll back the git repo and rebuild:

```bash
# 1. Find the last working commit
git log --oneline -10

# 2. Check out the known-good commit
git checkout <good-sha>

# 3. Rebuild and restart
docker compose up -d --build

# 4. Verify recovery
./scripts/smoke_test.sh
```

## Checking Logs

```bash
# Container logs (stdout/stderr)
docker logs frank-bot --tail 100

# Application log file (if mounted)
docker exec frank-bot cat /app/logs/frank_bot-api.log | tail -100

# Follow logs in real time
docker logs frank-bot -f
```

## Verifying Recovery

```bash
# 1. Run smoke test
./scripts/smoke_test.sh

# 2. Check /health manually
curl -s http://localhost:8000/health | jq .
# Expected: {"status": "healthy", "background_loop": {"running": true, ...}}

# 3. Check container status
docker ps --filter name=frank-bot

# 4. Watch for errors in logs
docker logs frank-bot --tail 50 | grep -i error
```

## Common Failure Scenarios

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `/health` returns `"status": "degraded"` | Vault unreachable | Check Vault connectivity, verify `VAULT_ADDR`/role credentials |
| `/health` returns `"status": "unhealthy"` | Background loop crashed | Check logs for crash_error, likely a code bug — rollback |
| Container exits immediately | Import/syntax error in new code | Check `docker logs frank-bot`, rollback |
| Container starts but no `/health` | Port binding issue or app crash during startup | Check `docker ps -a`, `docker logs frank-bot` |
| `background_loop.start_failed: true` | OpenAI/Telegram config missing | Check Vault secrets, may need to fix config |

## Prevention

Before deploying, run the smoke test locally:

```bash
docker compose up -d --build
./scripts/smoke_test.sh
docker compose down
```
