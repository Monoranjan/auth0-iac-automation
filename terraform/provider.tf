terraform {
  required_version = ">= 1.5.0"

  required_providers {
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.4"
    }
  }

  # State stored in Git — managed by CI/CD via local backend
  # The CI pipeline commits terraform.tfstate back to the repo after apply.
  backend "local" {
    path = "../states/terraform.tfstate"
  }
}

provider "auth0" {
  domain        = var.auth0_domain
  client_id     = var.auth0_client_id
  client_secret = var.auth0_client_secret
}
