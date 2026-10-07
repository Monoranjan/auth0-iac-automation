# -------------------------------------------------------
# Auth0 Provider credentials (injected via CI/CD secrets)
# -------------------------------------------------------
variable "auth0_domain" {
  description = "Auth0 tenant domain (e.g. dev-xyz.us.auth0.com)"
  type        = string
}

variable "auth0_client_id" {
  description = "Client ID of the Machine-to-Machine app in Auth0 with Management API access"
  type        = string
  sensitive   = true
}

variable "auth0_client_secret" {
  description = "Client Secret of the M2M app"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Deployment environment: dev | staging | prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}
