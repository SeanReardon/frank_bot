# =============================================================================
# Vault Policies
# =============================================================================

# API policy - can read frank-bot secrets
resource "vault_policy" "api" {
  name   = "frank-bot-api"
  policy = <<-EOT
    # Read frank-bot secrets
    path "secret/data/frank-bot/*" {
      capabilities = ["read"]
    }
  EOT
}
