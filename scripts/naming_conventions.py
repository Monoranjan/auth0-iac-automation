"""
Naming convention rules for Auth0 IaC resources.
Enforces the pattern: {env}-{resource_type}-{purpose}-v{version}
"""

import re
import yaml
from pathlib import Path

CONVENTIONS_FILE = Path(__file__).parent.parent / "naming_conventions.yaml"


def load_conventions() -> dict:
    with open(CONVENTIONS_FILE) as f:
        return yaml.safe_load(f)


def slugify(text: str) -> str:
    """Convert text to lowercase-hyphen slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def sanitize_tf_id(text: str) -> str:
    """Convert to valid Terraform identifier (underscores, no leading digit)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w]", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("_")
    if text and text[0].isdigit():
        text = "r_" + text
    return text


def build_resource_name(env: str, resource_type: str, purpose: str, version: int = 1) -> str:
    """Build the Auth0 display name following naming conventions."""
    conventions = load_conventions()
    envs = conventions["environments"]
    types = conventions["resource_types"]

    if env not in envs:
        raise ValueError(f"Environment '{env}' not in allowed list: {envs}")
    if resource_type not in types:
        raise ValueError(f"Resource type '{resource_type}' not in allowed list: {list(types.keys())}")

    purpose_slug = slugify(purpose)
    return f"{env}-{resource_type}-{purpose_slug}-v{version}"


def build_tf_resource_id(env: str, resource_type: str, purpose: str, version: int = 1) -> str:
    """Build Terraform resource ID (no hyphens, underscores)."""
    purpose_slug = sanitize_tf_id(purpose)
    return f"{resource_type}_{env}_{purpose_slug}_v{version}"


def build_tf_filename(resource_type: str, env: str, purpose: str, version: int = 1) -> str:
    """Build the Terraform file name."""
    purpose_slug = sanitize_tf_id(purpose)
    return f"{resource_type}_{env}_{purpose_slug}_v{version}.tf"


def validate_name(name: str) -> bool:
    """Validate a resource name against conventions."""
    conventions = load_conventions()
    pattern = r"^(dev|staging|prod)-[a-z]+-[a-z0-9-]+-v\d+$"
    return bool(re.match(pattern, name))


def detect_trigger(requirement_text: str) -> dict:
    """Detect the Auth0 trigger from requirement text."""
    conventions = load_conventions()
    text_lower = requirement_text.lower()
    for trigger_key, trigger_config in conventions["triggers"].items():
        for keyword in trigger_config["keywords"]:
            if keyword in text_lower:
                return {"key": trigger_key, **trigger_config}
    # Default to post-login
    return {
        "key": "post_login",
        "id": "post-login",
        "version": "v3",
        "keywords": [],
    }


def detect_client_type(requirement_text: str) -> dict:
    """Detect Auth0 client type from requirement text."""
    conventions = load_conventions()
    text_lower = requirement_text.lower()
    for type_key, type_config in conventions["client_types"].items():
        for keyword in type_config["keywords"]:
            if keyword in text_lower:
                return {"key": type_key, **type_config}
    # Default to SPA
    return {"key": "spa", "app_type": "spa", "keywords": []}


if __name__ == "__main__":
    # Quick self-test
    name = build_resource_name("prod", "action", "MFA Enforcement")
    print(f"Resource name : {name}")
    print(f"TF resource ID: {build_tf_resource_id('prod', 'action', 'MFA Enforcement')}")
    print(f"TF filename   : {build_tf_filename('action', 'prod', 'MFA Enforcement')}")
    print(f"Valid?        : {validate_name(name)}")
