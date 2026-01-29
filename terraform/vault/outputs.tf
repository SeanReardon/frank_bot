# =============================================================================
# Outputs
# =============================================================================

output "api_role_id" {
  value       = vault_approle_auth_backend_role.api.role_id
  description = "API AppRole role_id (not secret)"
}

output "api_secret_id" {
  value       = vault_approle_auth_backend_role_secret_id.api.secret_id
  description = "API AppRole secret_id"
  sensitive   = true
}

output "setup_instructions" {
  value = <<-EOT
    Add these to /home/frank_bot/.env on the server:
    
    VAULT_ADDR=https://vault.concordia.contrived.com:8200
    VAULT_ROLE_ID=${vault_approle_auth_backend_role.api.role_id}
    VAULT_SECRET_ID=<run: terraform output -raw api_secret_id>
  EOT
  description = "Instructions for configuring frank_bot to use Vault"
}
