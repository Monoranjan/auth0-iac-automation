variable "name" {
  description = "Auth0 Action display name (follows naming convention)"
  type        = string
}

variable "runtime" {
  description = "Node.js runtime version"
  type        = string
  default     = "node18"
}

variable "code" {
  description = "JavaScript action code"
  type        = string
}

variable "trigger_id" {
  description = "Auth0 trigger ID (e.g. post-login)"
  type        = string
}

variable "trigger_version" {
  description = "Auth0 trigger version"
  type        = string
  default     = "v3"
}

variable "deploy" {
  description = "Whether to deploy the action immediately"
  type        = bool
  default     = true
}

variable "secrets" {
  description = "Action secrets"
  type = list(object({
    name  = string
    value = string
  }))
  default   = []
  sensitive = true
}

variable "dependencies" {
  description = "npm package dependencies"
  type = list(object({
    name    = string
    version = string
  }))
  default = []
}
