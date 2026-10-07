resource "auth0_action" "this" {
  name    = var.name
  runtime = var.runtime
  deploy  = var.deploy
  code    = var.code

  dynamic "secrets" {
    for_each = var.secrets
    content {
      name  = secrets.value.name
      value = secrets.value.value
    }
  }

  dynamic "dependencies" {
    for_each = var.dependencies
    content {
      name    = dependencies.value.name
      version = dependencies.value.version
    }
  }

  supported_triggers {
    id      = var.trigger_id
    version = var.trigger_version
  }
}
