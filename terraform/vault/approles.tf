# =============================================================================
# Vault AppRoles
# =============================================================================

# API AppRole
resource "vault_approle_auth_backend_role" "api" {
  backend        = "approle"
  role_name      = "frank-bot-api"
  token_policies = [vault_policy.api.name]
  token_ttl      = 3600   # 1 hour
  token_max_ttl  = 14400  # 4 hours
}

# Generate secret_id for API
resource "vault_approle_auth_backend_role_secret_id" "api" {
  backend   = "approle"
  role_name = vault_approle_auth_backend_role.api.role_name
}
