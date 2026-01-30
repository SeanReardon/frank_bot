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
    oauth_token   = var.swarm_oauth_token
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
