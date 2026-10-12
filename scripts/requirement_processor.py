"""
Auth0 IaC Automation - Requirement Processor
=============================================
Reads a plain-text business requirement, calls an AI model to parse it,
generates Terraform HCL with naming conventions, and optionally commits
to Git and opens a pull request.

Supported AI providers (set ONE of these env vars — free tiers available):
  GEMINI_API_KEY    — Google Gemini 1.5 Flash (free: 1500 req/day) [RECOMMENDED]
  GROQ_API_KEY      — Groq Llama 3.1 70B (free: 14400 req/day)
  ANTHROPIC_API_KEY — Claude Haiku (paid, ~$0.001/req)

Usage:
  python scripts/requirement_processor.py --env dev --requirement "Create an MFA enforcement action for login"
  python scripts/requirement_processor.py --env prod --file requirements/mfa_action.txt
  python scripts/requirement_processor.py --env dev --file requirements/sample_requirement.txt --create-pr
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Ensure scripts/ is on the path when run from repo root
sys.path.insert(0, str(Path(__file__).parent))
from naming_conventions import (
    build_resource_name,
    build_tf_filename,
    build_tf_resource_id,
    detect_client_type,
    detect_trigger,
    slugify,
)
from terraform_generator import (
    generate_action,
    generate_api,
    generate_client,
    generate_outputs,
    generate_role,
    generate_variable_block,
    write_terraform_file,
)

REPO_ROOT = Path(__file__).parent.parent
CONVENTIONS_FILE = REPO_ROOT / "naming_conventions.yaml"

SYSTEM_PROMPT = """\
You are an Auth0 infrastructure expert. You parse plain-English business requirements
and output a structured JSON plan for Auth0 resources to create using Terraform.

Given a requirement, output ONLY a JSON object (no markdown fences, no extra text).

The JSON schema:
{
  "resources": [
    {
      "type": "action|client|api|role",
      "purpose": "short kebab-case purpose label (2-4 words)",
      "description": "one-sentence description",
      "details": {
        // For type=action:
        "trigger": "post-login|pre-user-registration|post-user-registration|credentials-exchange|send-phone-message",
        "trigger_version": "v3|v2|v1",
        "code_description": "What the JS action code should do (2-3 sentences)",
        "code": "Full Node.js 18 action code using Auth0 Actions API",
        "secrets": [{"name": "SECRET_NAME", "var_name": "secret_var_name", "description": "what this secret is"}],
        "dependencies": [{"name": "npm-package", "version": "^x.y.z"}],

        // For type=client:
        "app_type": "spa|native|regular_web|non_interactive",
        "callbacks": ["https://localhost:3000/callback"],
        "allowed_logout_urls": ["https://localhost:3000"],
        "web_origins": ["https://localhost:3000"],
        "grant_types": ["authorization_code", "refresh_token"],

        // For type=api:
        "identifier": "https://api.example.com/v1",
        "scopes": [{"value": "read:items", "description": "Read items"}],

        // For type=role:
        "role_description": "what this role can do"
      }
    }
  ],
  "summary": "One-sentence summary of what will be deployed"
}

Auth0 Actions code must follow this pattern for post-login:
exports.onExecutePostLogin = async (event, api) => {
  // logic here
};

Use event.user, event.authentication, api.access.deny(), api.multifactor.enable(), api.redirect.sendUserTo(), etc.
For credentials-exchange: exports.onExecuteCredentialsExchange = async (event, api) => { ... };
For pre-user-registration: exports.onExecutePreUserRegistration = async (event, api) => { ... };
"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that some models add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        # Remove trailing fence
        if "```" in text:
            text = text[:text.rfind("```")]
    return text.strip()


def _detect_provider() -> str:
    """Return which AI provider to use based on available env vars."""
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def call_ai(requirement: str) -> dict:
    """Call an AI model to parse the requirement. Uses whichever provider key is set."""
    provider = _detect_provider()
    prompt = f"Business requirement:\n\n{requirement}\n\nGenerate the JSON plan."

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(prompt)
        raw = _strip_fences(response.text)

    elif provider == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        response = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0,
        )
        raw = _strip_fences(response.choices[0].message.content)

    elif provider == "anthropic":
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_fences(message.content[0].text)

    else:
        print("[ERROR] No AI provider key found. Set one of:")
        print("  export GEMINI_API_KEY=...   (free, recommended)")
        print("  export GROQ_API_KEY=...     (free)")
        print("  export ANTHROPIC_API_KEY=... (paid)")
        sys.exit(1)

    print(f"  [AI] Provider: {provider}")
    return json.loads(raw)


def generate_action_code_stub(description: str) -> str:
    """Fallback: generate a minimal action code stub."""
    return f"""\
/**
 * Auth0 Action
 * {description}
 *
 * Generated by Auth0 IaC Automation
 */
exports.onExecutePostLogin = async (event, api) => {{
  // TODO: Implement logic
  // Description: {description}
  //
  // Available: event.user, event.authentication, event.tenant
  // Actions:   api.access.deny(), api.multifactor.enable(), api.redirect.sendUserTo()
}};
"""


def process_resources(plan: dict, env: str) -> list[Path]:
    """Generate Terraform files for all resources in the plan."""
    generated_files = []
    extra_variables = []

    for resource in plan.get("resources", []):
        rtype = resource["type"]
        purpose = resource["purpose"]
        details = resource.get("details", {})
        version = 1

        display_name = build_resource_name(env, rtype, purpose, version)
        tf_id = build_tf_resource_id(env, rtype, purpose, version)
        filename = build_tf_filename(rtype, env, purpose, version)

        print(f"  [+] {rtype.upper()}: {display_name}")
        print(f"      TF ID   : {tf_id}")
        print(f"      File    : {filename}")

        hcl_parts = [
            f"# Auto-generated by Auth0 IaC Automation\n"
            f"# Requirement processed: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            f"# Purpose: {resource.get('description', purpose)}\n\n"
        ]

        if rtype == "action":
            trigger_id = details.get("trigger", "post-login")
            trigger_version = details.get("trigger_version", "v3")
            code = details.get("code") or generate_action_code_stub(resource.get("description", purpose))
            secrets = details.get("secrets", [])
            dependencies = details.get("dependencies", [])

            hcl_parts.append(
                generate_action(tf_id, display_name, trigger_id, trigger_version, code, secrets, dependencies)
            )
            # Add variable blocks for secrets
            for s in secrets:
                extra_variables.append(
                    generate_variable_block(s["var_name"], s.get("description", s["name"]), sensitive=True)
                )

        elif rtype == "client":
            app_type = details.get("app_type", "spa")
            hcl_parts.append(
                generate_client(
                    tf_id,
                    display_name,
                    app_type,
                    description=resource.get("description", ""),
                    callbacks=details.get("callbacks", ["https://localhost:3000/callback"]),
                    allowed_logout_urls=details.get("allowed_logout_urls", ["https://localhost:3000"]),
                    web_origins=details.get("web_origins", ["https://localhost:3000"]),
                    grant_types=details.get("grant_types", ["authorization_code", "refresh_token"]),
                )
            )

        elif rtype == "api":
            identifier = details.get("identifier", f"https://api.example.com/{slugify(purpose)}")
            hcl_parts.append(generate_api(tf_id, display_name, identifier, scopes=details.get("scopes", [])))

        elif rtype == "role":
            hcl_parts.append(generate_role(tf_id, display_name, details.get("role_description", "")))

        hcl_parts.append(generate_outputs(tf_id, rtype, display_name))
        hcl = "\n".join(hcl_parts)
        path = write_terraform_file(filename, hcl)
        generated_files.append(path)
        print(f"      Written : {path.relative_to(REPO_ROOT)}\n")

    # Write extra variables to a shared file
    if extra_variables:
        vars_path = write_terraform_file("_generated_variables.tf", "\n".join(extra_variables))
        generated_files.append(vars_path)
        print(f"  [+] Variables written: {vars_path.relative_to(REPO_ROOT)}")

    return generated_files


def git_create_branch_and_pr(env: str, summary: str, files: list[Path]) -> None:
    """Commit generated files to a new branch and create a GitHub PR."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    branch = f"feat/iac-{env}-{timestamp}"

    rel_files = [str(f.relative_to(REPO_ROOT)) for f in files]

    cmds = [
        ["git", "checkout", "-b", branch],
        ["git", "add"] + rel_files,
        [
            "git",
            "commit",
            "-m",
            f"feat(iac): {summary}\n\nGenerated by Auth0 IaC Automation\nEnvironment: {env}",
        ],
        ["git", "push", "-u", "origin", branch],
    ]

    for cmd in cmds:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [!] Command failed: {' '.join(cmd)}")
            print(f"      {result.stderr}")
            return
        print(f"  [git] {' '.join(cmd[:3])}...")

    # Create PR using gh CLI
    pr_body = (
        f"## Summary\n\n{summary}\n\n"
        "## Changes\n\n"
        + "\n".join(f"- `{f}`" for f in rel_files)
        + "\n\n## Plan\n\nThis PR was auto-generated. Review the Terraform plan output below "
        "before merging to trigger `terraform apply`.\n\n"
        "🤖 Generated with [Auth0 IaC Automation](https://github.com/Monoranjan/auth0-iac-automation)"
    )

    pr_cmd = [
        "gh", "pr", "create",
        "--title", f"feat(iac): {summary} [{env}]",
        "--body", pr_body,
        "--label", "terraform,auto-generated",
    ]
    result = subprocess.run(pr_cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"\n  [PR] Created: {result.stdout.strip()}")
    else:
        print(f"\n  [!] PR creation failed (gh CLI may not be configured): {result.stderr}")
        print(f"  [hint] Push your branch and open PR manually: git push origin {branch}")


def main():
    parser = argparse.ArgumentParser(
        description="Process a business requirement and generate Auth0 Terraform resources."
    )
    parser.add_argument("--env", required=True, choices=["dev", "staging", "prod"],
                        help="Target environment")
    parser.add_argument("--requirement", "-r", type=str,
                        help="Inline requirement text")
    parser.add_argument("--file", "-f", type=Path,
                        help="Path to a requirement text file")
    parser.add_argument("--create-pr", action="store_true",
                        help="Auto-commit and create a GitHub PR after generation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the AI plan but do not write files")
    args = parser.parse_args()

    if not args.requirement and not args.file:
        parser.error("Provide --requirement or --file")

    requirement = args.requirement
    if args.file:
        requirement = Path(args.file).read_text(encoding="utf-8").strip()

    print("\n" + "=" * 60)
    print("  Auth0 IaC Automation - Requirement Processor")
    print("=" * 60)
    print(f"  Environment : {args.env}")
    print(f"  Requirement :\n    {requirement[:200]}{'...' if len(requirement) > 200 else ''}")
    print("=" * 60 + "\n")

    print("[1/3] Sending requirement to AI for analysis...")
    plan = call_ai(requirement)
    summary = plan.get("summary", "Auth0 resource changes")

    print(f"\n[AI Plan] {summary}")
    print(f"  Resources to create: {len(plan.get('resources', []))}")
    for r in plan.get("resources", []):
        print(f"  - {r['type'].upper()}: {r['purpose']} — {r.get('description', '')}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        print(json.dumps(plan, indent=2))
        return

    print("\n[2/3] Generating Terraform files...")
    generated = process_resources(plan, args.env)

    if not generated:
        print("[!] No files were generated.")
        sys.exit(1)

    print(f"[3/3] Done. {len(generated)} file(s) generated in terraform/generated/")

    if args.create_pr:
        print("\n[PR] Creating branch and pull request...")
        git_create_branch_and_pr(args.env, summary, generated)

    print("\nNext steps:")
    print("  1. Review generated files in terraform/generated/")
    print("  2. Run: cd terraform && terraform init && terraform plan -var-file=environments/dev/terraform.tfvars")
    print("  3. Commit and push — GitHub Actions will run plan/apply automatically")
    print()


if __name__ == "__main__":
    main()
