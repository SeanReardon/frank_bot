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

# Telegram Bot (for notifications - separate from Telethon user client)
variable "telegram_bot_token" {
  type        = string
  description = "Telegram Bot token from BotFather"
  sensitive   = true
  default     = ""
}

variable "telegram_bot_chat_id" {
  type        = string
  description = "Chat ID for bot notifications (Sean's Telegram user ID)"
  sensitive   = true
  default     = ""
}

# OpenAI
variable "openai_api_key" {
  type        = string
  description = "OpenAI API key for gpt-5.2 agent reasoning"
  sensitive   = true
}

# Claudia (autonomous agent orchestrator)
variable "claudia_api_url" {
  type        = string
  description = "Claudia API base URL"
  default     = "https://claudia.contrived.com"
}

variable "claudia_api_key" {
  type        = string
  description = "Claudia API key for authentication"
  sensitive   = true
  default     = ""
}

# Earshot (transcript search and LLM queries)
variable "earshot_api_url" {
  type        = string
  description = "Earshot API base URL"
  default     = "https://earshot-api.contrived.com"
}

variable "earshot_api_key" {
  type        = string
  description = "Earshot API key for X-API-Key header authentication"
  sensitive   = true
  default     = ""
}

# Android phone automation
variable "android_device_serial" {
  type        = string
  description = "ADB USB serial of the Android device (preferred transport; from `adb devices`)"
  sensitive   = true
  default     = ""
}

variable "android_adb_host" {
  type        = string
  description = "IP address for ADB over TCP (wireless debugging fallback)"
  # Intentionally no default; set explicitly if you use TCP/IP ADB.
  # Historical value (removed to avoid confusion): 10.0.0.95
  default     = ""
}

variable "android_adb_port" {
  type        = string
  description = "ADB TCP port (wireless debugging fallback; default: 5555)"
  default     = "5555"
}

variable "android_llm_api_key" {
  type        = string
  description = "Optional API key override for Android phone automation LLM"
  sensitive   = true
  default     = ""
}

# Actions API authentication
variable "actions_api_key" {
  type        = string
  description = "API key for authenticating requests to frank-bot (X-API-Key header)"
  sensitive   = true
}

# Email / SMTP (daily digest + notifications)
variable "smtp_host" {
  type        = string
  description = "SMTP server hostname (e.g., smtp.gmail.com)"
  default     = ""
}

variable "smtp_port" {
  type        = string
  description = "SMTP server port (e.g., 587)"
  default     = "587"
}

variable "smtp_user" {
  type        = string
  description = "SMTP username / from-address"
  sensitive   = true
  default     = ""
}

variable "smtp_password" {
  type        = string
  description = "SMTP password / app password"
  sensitive   = true
  default     = ""
}

variable "digest_email_to" {
  type        = string
  description = "Default recipient email for digests/alerts"
  sensitive   = true
  default     = ""
}

variable "digest_time" {
  type        = string
  description = "Daily digest time (UTC, HH:MM, 24h)"
  default     = "08:00"
}
