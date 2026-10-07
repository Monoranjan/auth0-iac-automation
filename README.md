# Auth0 IaC Automation

> **Plain English → Terraform → Auth0 Tenant**, automated with GitHub Actions.

Write a business requirement in plain text, and this system uses Claude AI to generate
correctly-named Terraform resources and deploy them to your Auth0 tenant via CI/CD.

---

## How It Works

```
Business Requirement (text)
        │
        ▼
┌─────────────────────┐
│  requirement_       │  Python + Claude AI (claude-haiku)
│  processor.py       │  Parses intent, generates resource plan
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Terraform HCL      │  Naming convention enforced:
│  (terraform/        │  {env}-{type}-{purpose}-v{version}
│   generated/)       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  GitHub PR          │  Auto-created branch + PR
│                     │  terraform plan posted as comment
└────────┬────────────┘
         │  merge
         ▼
┌─────────────────────┐
│  terraform apply    │  GitHub Actions deploys to Auth0
│  (GitHub Actions)   │  State committed back to Git
└─────────────────────┘
```

---

## Naming Convention

All Auth0 resources follow this pattern:

```
{env}-{resource_type}-{purpose}-v{version}
```

| Environment | Resource Type | Example Name |
|-------------|---------------|--------------|
| `dev`       | `action`      | `dev-action-mfa-enforcement-v1` |
| `prod`      | `client`      | `prod-client-spa-dashboard-v1` |
| `staging`   | `api`         | `staging-api-inventory-service-v1` |
| `dev`       | `role`        | `dev-role-admin-v1` |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Terraform 1.5+
- `gh` CLI (GitHub CLI) — optional, for auto-PR creation
- Auth0 account (free tier works)
- [Anthropic API key](https://console.anthropic.com) (free tier: $5 credit)

### 1. Clone and install

```bash
git clone https://github.com/Monoranjan/auth0-iac-automation
cd auth0-iac-automation
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Process a requirement

```bash
# From inline text
python scripts/requirement_processor.py \
  --env dev \
  --requirement "Create an MFA enforcement action for all users during login"

# From a text file
python scripts/requirement_processor.py \
  --env dev \
  --file requirements/sample_requirement.txt

# Dry run (just show the AI plan, don't write files)
python scripts/requirement_processor.py \
  --env dev \
  --file requirements/sample_requirement.txt \
  --dry-run

# Auto-create GitHub PR after generation
python scripts/requirement_processor.py \
  --env dev \
  --file requirements/sample_requirement.txt \
  --create-pr
```

### 4. Review and apply

```bash
cd terraform
terraform init
terraform plan -var-file=environments/dev/terraform.tfvars \
  -var auth0_domain=$AUTH0_DEV_DOMAIN \
  -var auth0_client_id=$AUTH0_DEV_CLIENT_ID \
  -var auth0_client_secret=$AUTH0_DEV_CLIENT_SECRET \
  -var environment=dev
```

---

## GitHub Actions Setup

### Required Secrets (Settings → Secrets → Actions)

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude AI API key |
| `AUTH0_DEV_DOMAIN` | Auth0 dev tenant domain (e.g. `dev-abc123.us.auth0.com`) |
| `AUTH0_DEV_CLIENT_ID` | M2M app Client ID with Management API access |
| `AUTH0_DEV_CLIENT_SECRET` | M2M app Client Secret |
| `AUTH0_PROD_DOMAIN` | (when ready for prod) |
| `AUTH0_PROD_CLIENT_ID` | (when ready for prod) |
| `AUTH0_PROD_CLIENT_SECRET` | (when ready for prod) |

### Setting up Auth0 M2M App for Terraform

1. Go to **Auth0 Dashboard → Applications → Create Application**
2. Choose **Machine to Machine**
3. Select **Auth0 Management API** and grant all scopes (or at minimum: `create:actions`, `update:actions`, `read:actions`, `create:clients`, etc.)
4. Copy the Domain, Client ID, and Client Secret into GitHub Secrets

### CI/CD Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `process-requirement.yml` | Push `.txt` to `requirements/`, or manual dispatch | Calls Claude AI, generates Terraform, creates PR |
| `terraform-plan.yml` | PR opened against `main` | Runs `terraform plan`, posts output as PR comment |
| `terraform-apply.yml` | Push to `main` (after PR merge) | Runs `terraform apply`, commits state back to Git |

### Manual trigger via GitHub UI

1. Go to **Actions → Process Requirement → Run workflow**
2. Enter your business requirement text
3. Select environment (`dev`, `staging`, `prod`)
4. Click **Run workflow** — a PR will be created automatically

---

## State Management

Terraform state is stored directly in this Git repository under `states/`.

- The `terraform-apply.yml` workflow commits the state file back after each apply using `[skip ci]` to prevent loops
- State is in the `local` backend pointing to `../states/terraform.tfstate`
- **For production use**: consider migrating to a remote backend (Terraform Cloud free tier, or an S3-compatible store)

---

## Project Structure

```
auth0-iac-automation/
├── .github/workflows/
│   ├── process-requirement.yml   # Requirement → Terraform → PR
│   ├── terraform-plan.yml        # PR validation
│   └── terraform-apply.yml       # Deploy on merge to main
├── scripts/
│   ├── requirement_processor.py  # Main CLI: text → Terraform
│   ├── naming_conventions.py     # Naming rules + validators
│   └── terraform_generator.py    # HCL code generation
├── terraform/
│   ├── provider.tf               # Auth0 provider + local backend
│   ├── variables.tf              # Shared variables
│   ├── modules/
│   │   └── auth0_action/         # Reusable action module
│   ├── environments/
│   │   ├── dev/terraform.tfvars
│   │   └── prod/terraform.tfvars
│   └── generated/                # Auto-generated .tf files (committed)
├── states/                       # Terraform state (committed by CI)
├── requirements/                 # Input requirement text files
├── naming_conventions.yaml       # Convention config
└── requirements.txt              # Python deps (anthropic, pyyaml)
```

---

## Supported Auth0 Resources

| Type keyword | Auth0 Resource | Terraform |
|---|---|---|
| `action` | Auth0 Actions | `auth0_action` |
| `client` | Applications (SPA, M2M, Native, Web) | `auth0_client` |
| `api` | APIs / Resource Servers | `auth0_resource_server` |
| `role` | RBAC Roles | `auth0_role` |

---

## Example Requirements

**MFA Action:**
```
Create an Auth0 action that enforces MFA for admin users during login.
```

**SPA Application:**
```
Register a new single-page React dashboard application for the dev environment.
It will run on localhost:3000 during development.
```

**API Resource Server:**
```
Create an Auth0 API for our inventory microservice in staging.
It needs read:items and write:items scopes.
```

**RBAC Role:**
```
Add an admin role to the prod environment for users who manage the tenant settings.
```
