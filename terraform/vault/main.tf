# =============================================================================
# Frank Bot Vault Configuration
# =============================================================================
# Configures Vault secrets, policies, and AppRoles for Frank Bot.
# Apply with: terraform apply -var-file=terraform.tfvars
# =============================================================================

terraform {
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "~> 4.0"
    }
  }
}

provider "vault" {
  # Address from VAULT_ADDR environment variable
  # Token from VAULT_TOKEN environment variable
}
