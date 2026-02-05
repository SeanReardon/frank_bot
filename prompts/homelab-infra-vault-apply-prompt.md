# Homelab-Infra: Apply Frank Bot Vault Terraform

## Context

The frank_bot repository has been updated with new Vault secrets for Android phone automation and Actions API authentication. The terraform configuration needs to be applied from a machine with Vault access.

## Task

Apply the Vault terraform changes for frank_bot to create/update these secrets:
- `secret/frank-bot/android` - Android ADB connection config (host: 10.0.0.95, port: 5555)
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

3. **Verify the terraform.tfvars has the new variables** (should already be there from the commit):
   ```bash
   grep -E "android_|actions_api" terraform.tfvars
   ```
   
   Expected output should include:
   - `android_adb_host = "10.0.0.95"`
   - `android_adb_port = "5555"`
   - `actions_api_key = "f04ad182983a4361f95119cd8508034d2a604b623d45c0083c93eb736f2a9b78"`

4. **Ensure Vault environment is configured**:
   ```bash
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
- Frank-bot will load Android ADB config from Vault instead of env vars
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
