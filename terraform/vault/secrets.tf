# =============================================================================
# Vault Secrets
# =============================================================================

# Stytch credentials (for session validation from contrived.com)
resource "vault_kv_secret_v2" "stytch" {
  mount = "secret"
  name  = "frank-bot/stytch"
  data_json = jsonencode({
    project_id = var.stytch_project_id
    secret     = var.stytch_secret
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Telegram API credentials
resource "vault_kv_secret_v2" "telegram" {
  mount = "secret"
  name  = "frank-bot/telegram"
  data_json = jsonencode({
    api_id   = var.telegram_api_id
    api_hash = var.telegram_api_hash
    phone    = var.telegram_phone
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Telnyx SMS credentials
resource "vault_kv_secret_v2" "telnyx" {
  mount = "secret"
  name  = "frank-bot/telnyx"
  data_json = jsonencode({
    api_key      = var.telnyx_api_key
    phone_number = var.telnyx_phone_number
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Google OAuth credentials
resource "vault_kv_secret_v2" "google" {
  mount = "secret"
  name  = "frank-bot/google"
  data_json = jsonencode({
    client_id     = var.google_client_id
    client_secret = var.google_client_secret
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Swarm/Foursquare credentials
resource "vault_kv_secret_v2" "swarm" {
  mount = "secret"
  name  = "frank-bot/swarm"
  data_json = jsonencode({
    oauth_token    = var.swarm_oauth_token
    # Prefer `api_key` to match `services/vault_client.py` + `config.py`.
    # Keep `foursquare_key` for backwards compatibility with older deployments.
    api_key        = var.foursquare_api_key
    foursquare_key = var.foursquare_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Telegram Bot credentials (for notifications - separate from Telethon user client)
resource "vault_kv_secret_v2" "telegram_bot" {
  mount = "secret"
  name  = "frank-bot/telegram-bot"
  data_json = jsonencode({
    token   = var.telegram_bot_token
    chat_id = var.telegram_bot_chat_id
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# OpenAI API credentials (for gpt-5.2 agent reasoning)
resource "vault_kv_secret_v2" "openai" {
  mount = "secret"
  name  = "frank-bot/openai"
  data_json = jsonencode({
    api_key = var.openai_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Claudia API credentials (autonomous agent orchestrator)
resource "vault_kv_secret_v2" "claudia" {
  mount = "secret"
  name  = "frank-bot/claudia"
  data_json = jsonencode({
    api_url = var.claudia_api_url
    api_key = var.claudia_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Earshot transcript API credentials
resource "vault_kv_secret_v2" "earshot" {
  mount = "secret"
  name  = "frank-bot/earshot"
  data_json = jsonencode({
    api_url = var.earshot_api_url
    api_key = var.earshot_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Android phone automation configuration
resource "vault_kv_secret_v2" "android" {
  mount = "secret"
  name  = "frank-bot/android"
  data_json = jsonencode({
    device_serial = var.android_device_serial
    adb_host      = var.android_adb_host
    adb_port      = var.android_adb_port
    llm_api_key   = var.android_llm_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Actions API key (for authenticating requests to frank-bot)
resource "vault_kv_secret_v2" "actions" {
  mount = "secret"
  name  = "frank-bot/actions"
  data_json = jsonencode({
    api_key = var.actions_api_key
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}

# Email / SMTP credentials (daily digest + notifications)
resource "vault_kv_secret_v2" "email" {
  mount = "secret"
  name  = "frank-bot/email"
  data_json = jsonencode({
    smtp_host       = var.smtp_host
    smtp_port       = var.smtp_port
    smtp_user       = var.smtp_user
    smtp_password   = var.smtp_password
    digest_email_to = var.digest_email_to
    digest_time     = var.digest_time
  })

  lifecycle {
    ignore_changes = [data_json]
  }
}
