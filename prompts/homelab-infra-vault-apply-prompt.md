# Homelab-Infra: Apply Frank Bot Vault Terraform

## Context

The frank_bot repository has been updated with new Vault secrets for Android phone automation and Actions API authentication. The terraform configuration needs to be applied from a machine with Vault access.

## Task

Apply the Vault terraform changes for frank_bot to create/update these secrets:
- `secret/frank-bot/android` - Android ADB connection config (**USB serial preferred**, TCP/IP fallback optional)
- `secret/frank-bot/actions` - Actions API key for authentication

## Steps

1. **Pull the latest frank_bot code** (the terraform files have been updated):
   ```bash
   cd ~/dev/frank_bot  # or wherever frank_bot is cloned
   git pull origin main
   ```

2. **Navigate to the Vault terraform directory**:
   ```bash
   cd terraform/vault
   ```

3. **Add the new variables to terraform.tfvars** (this file is gitignored, so add manually):
   ```bash
   cat >> terraform.tfvars << 'EOF'

# Android phone automation (ADB)
# Preferred: USB serial from `adb devices` (onlogic-closet currently: 48151FDKD001UD)
android_device_serial = "48151FDKD001UD"
#
# Optional fallback: wireless debugging host/port
# android_adb_host = "10.0.0.95"
# android_adb_port = "5555"

# Actions API key (for X-API-Key header authentication)
actions_api_key = "<ACTIONS_API_KEY>"
EOF
   ```
   
   Verify they were added:
   ```bash
   grep -E "android_|actions_api" terraform.tfvars
   ```

4. **Ensure Vault environment is configured**:
   ```bash
   export VAULT_ADDR="https://vault.concordia.contrived.com:8200"
   echo $VAULT_ADDR
   vault status
   ```

5. **Run terraform apply**:
   ```bash
   terraform init
   terraform plan  # Review changes first
   terraform apply -auto-approve
   ```

6. **Verify the secrets were created**:
   ```bash
   vault kv get secret/frank-bot/android
   vault kv get secret/frank-bot/actions
   ```

## Expected Outcome

After applying:
- Frank-bot will load Android ADB config from Vault (USB serial preferred)
- Frank-bot will load ACTIONS_API_KEY from Vault instead of env vars
- The container may need to be restarted to pick up the new config:
  ```bash
  docker-compose restart frank-bot  # or however frank-bot is deployed
  ```

## Verification

Test that frank-bot can read the secrets:
```bash
curl -s "https://frank-bot-api.contrived.com/actions/androidPhone/health"
```

Should return connected: true with device info.
