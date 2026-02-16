# Frank Bot Vault Configuration

Terraform configuration for managing Frank Bot secrets in HashiCorp Vault.

## Prerequisites

1. Vault CLI installed
2. Access to `vault.concordia.contrived.com` with admin privileges
3. Terraform 1.0+

## Setup

1. **Authenticate to Vault:**
   ```bash
   export VAULT_ADDR=https://vault.concordia.contrived.com:8200
   vault login  # Use your preferred method
   ```

2. **Create terraform.tfvars:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with actual values
   ```

3. **Get Stytch credentials from contrived-site:**
   ```bash
   # The Stytch project_id and secret must match contrived-site production
   # so frank_bot can validate sessions created by contrived-site
   vault kv get contrived-site/prod/stytch
   ```

4. **Initialize and apply:**
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

5. **Get AppRole credentials for frank_bot:**
   ```bash
   terraform output api_role_id
   terraform output -raw api_secret_id
   ```

6. **Update frank_bot's .env on the server:**
   ```bash
   ssh seanr@onlogic-closet
   sudo -u frank_bot vim /home/frank_bot/.env
   
   # Add:
   VAULT_ADDR=https://vault.concordia.contrived.com:8200
   VAULT_ROLE_ID=<from terraform output>
   VAULT_SECRET_ID=<from terraform output -raw api_secret_id>
   ```

7. **Restart frank_bot:**
   ```bash
   sudo -u frank_bot docker compose restart frank-bot
   ```

## Secrets Stored

| Path | Description |
|------|-------------|
| `frank-bot/stytch` | Stytch project credentials (for session validation) |
| `frank-bot/telegram` | Telegram API credentials |
| `frank-bot/telegram-bot` | Telegram Bot API token + default chat_id (notifications) |
| `frank-bot/telnyx` | Telnyx SMS credentials |
| `frank-bot/google` | Google OAuth credentials |
| `frank-bot/swarm` | Swarm/Foursquare credentials |
| `frank-bot/openai` | OpenAI API key (jorb agent reasoning) |
| `frank-bot/claudia` | Claudia API URL + API key |
| `frank-bot/android` | Android automation config (USB `device_serial` preferred; `adb_host`/`adb_port` optional fallback) |
| `frank-bot/actions` | Actions API key (X-API-Key auth) |
| `frank-bot/email` | SMTP + digest notification settings |

## Rotating Secrets

To update a secret:

1. Update the variable in `terraform.tfvars`
2. Remove the `ignore_changes` lifecycle rule temporarily (or use `terraform state rm`)
3. Apply: `terraform apply`
4. Restart frank_bot to pick up new credentials

## Troubleshooting

**"permission denied" on Vault:**
- Ensure your Vault token has admin privileges
- Check that the policy grants access to `secret/data/frank-bot/*`

**frank_bot can't read secrets:**
- Verify VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID in .env
- Check Vault audit logs: `vault audit list`
- Test manually: `vault read secret/data/frank-bot/stytch`
