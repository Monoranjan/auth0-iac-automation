"""
Generates Terraform HCL files from parsed Auth0 resource definitions.
"""

import json
from pathlib import Path
from typing import Any

GENERATED_DIR = Path(__file__).parent.parent / "terraform"


def _indent(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


def generate_action(
    tf_id: str,
    display_name: str,
    trigger_id: str,
    trigger_version: str,
    code: str,
    secrets: list[dict] | None = None,
    dependencies: list[dict] | None = None,
) -> str:
    """Generate Terraform HCL for an auth0_action resource."""
    secrets_block = ""
    if secrets:
        for s in secrets:
            secrets_block += f"""
  secrets {{
    name  = "{s['name']}"
    value = var.{s['var_name']}
  }}
"""

    deps_block = ""
    if dependencies:
        for d in dependencies:
            version_str = f'"{d["version"]}"' if d.get("version") else '"*"'
            deps_block += f"""
  dependencies {{
    name    = "{d['name']}"
    version = {version_str}
  }}
"""

    # Escape the code for heredoc
    code_escaped = code.replace("${", "$${")  # Terraform heredoc escape

    return f"""resource "auth0_action" "{tf_id}" {{
  name    = "{display_name}"
  runtime = "node18"
  deploy  = true

  code = <<-EOT
{_indent(code, 4)}
  EOT
{secrets_block}{deps_block}
  supported_triggers {{
    id      = "{trigger_id}"
    version = "{trigger_version}"
  }}
}}
"""


def generate_client(
    tf_id: str,
    display_name: str,
    app_type: str,
    description: str = "",
    callbacks: list[str] | None = None,
    allowed_logout_urls: list[str] | None = None,
    web_origins: list[str] | None = None,
    grant_types: list[str] | None = None,
) -> str:
    """Generate Terraform HCL for an auth0_client resource."""
    callbacks_str = ""
    if callbacks:
        urls = ", ".join(f'"{u}"' for u in callbacks)
        callbacks_str = f"\n  callbacks             = [{urls}]"

    logout_str = ""
    if allowed_logout_urls:
        urls = ", ".join(f'"{u}"' for u in allowed_logout_urls)
        logout_str = f"\n  allowed_logout_urls   = [{urls}]"

    origins_str = ""
    if web_origins:
        urls = ", ".join(f'"{u}"' for u in web_origins)
        origins_str = f"\n  web_origins           = [{urls}]"

    grants_str = ""
    if grant_types:
        grants = ", ".join(f'"{g}"' for g in grant_types)
        grants_str = f"\n  grant_types           = [{grants}]"

    desc_str = f'\n  description           = "{description}"' if description else ""

    return f"""resource "auth0_client" "{tf_id}" {{
  name                  = "{display_name}"
  app_type              = "{app_type}"{desc_str}{callbacks_str}{logout_str}{origins_str}{grants_str}

  oidc_conformant = true
  jwt_configuration {{
    alg = "RS256"
  }}
}}
"""


def generate_api(
    tf_id: str,
    display_name: str,
    identifier: str,
    scopes: list[dict] | None = None,
    signing_alg: str = "RS256",
) -> str:
    """Generate Terraform HCL for an auth0_resource_server (API)."""
    scopes_block = ""
    if scopes:
        for s in scopes:
            desc = s.get("description", s["value"])
            scopes_block += f"""
  scopes {{
    value       = "{s['value']}"
    description = "{desc}"
  }}
"""

    return f"""resource "auth0_resource_server" "{tf_id}" {{
  name        = "{display_name}"
  identifier  = "{identifier}"
  signing_alg = "{signing_alg}"

  allow_offline_access                            = false
  token_lifetime                                  = 86400
  skip_consent_for_verifiable_first_party_clients = true
{scopes_block}}}
"""


def generate_role(
    tf_id: str,
    display_name: str,
    description: str = "",
) -> str:
    """Generate Terraform HCL for an auth0_role resource."""
    desc_str = f'\n  description = "{description}"' if description else ""
    return f"""resource "auth0_role" "{tf_id}" {{
  name        = "{display_name}"{desc_str}
}}
"""


def generate_outputs(tf_id: str, resource_type: str, display_name: str) -> str:
    """Generate Terraform output blocks."""
    resource_map = {
        "action": "auth0_action",
        "client": "auth0_client",
        "api": "auth0_resource_server",
        "role": "auth0_role",
    }
    tf_resource = resource_map.get(resource_type, f"auth0_{resource_type}")

    outputs = {
        "action": [("id", "id"), ("name", "name")],
        "client": [("id", "client_id"), ("name", "name")],
        "api": [("id", "id"), ("identifier", "identifier")],
        "role": [("id", "id"), ("name", "name")],
    }

    lines = [f"# Outputs for {display_name}"]
    for label, attr in outputs.get(resource_type, [("id", "id")]):
        lines.append(f"""
output "{tf_id}_{label}" {{
  value = {tf_resource}.{tf_id}.{attr}
}}""")
    return "\n".join(lines) + "\n"


def write_terraform_file(filename: str, content: str) -> Path:
    """Write generated Terraform content to the generated/ directory."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / filename
    with open(path, "w") as f:
        f.write(content)
    return path


def generate_variable_block(name: str, description: str, sensitive: bool = False) -> str:
    sensitive_str = "\n  sensitive   = true" if sensitive else ""
    return f"""variable "{name}" {{
  description = "{description}"{sensitive_str}
  type        = string
}}
"""
