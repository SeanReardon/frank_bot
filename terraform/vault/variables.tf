# =============================================================================
# Variables
# =============================================================================

# Stytch (for session validation)
variable "stytch_project_id" {
  type        = string
  description = "Stytch project ID (same as contrived-site production)"
  sensitive   = true
}

variable "stytch_secret" {
  type        = string
  description = "Stytch secret (same as contrived-site production)"
  sensitive   = true
}

# Telegram
variable "telegram_api_id" {
  type        = string
  description = "Telegram API ID from my.telegram.org"
  sensitive   = true
}

variable "telegram_api_hash" {
  type        = string
  description = "Telegram API Hash from my.telegram.org"
  sensitive   = true
}

variable "telegram_phone" {
  type        = string
  description = "Telegram phone number in E.164 format"
  sensitive   = true
}

# Telnyx SMS
variable "telnyx_api_key" {
  type        = string
  description = "Telnyx API key for SMS"
  sensitive   = true
}

variable "telnyx_phone_number" {
  type        = string
  description = "Telnyx phone number for sending SMS"
  sensitive   = true
}

# Google OAuth
variable "google_client_id" {
  type        = string
  description = "Google OAuth client ID"
  sensitive   = true
}

variable "google_client_secret" {
  type        = string
  description = "Google OAuth client secret"
  sensitive   = true
}

# Swarm/Foursquare
variable "swarm_oauth_token" {
  type        = string
  description = "Swarm OAuth token"
  sensitive   = true
}

variable "foursquare_api_key" {
  type        = string
  description = "Foursquare API key"
  sensitive   = true
}
