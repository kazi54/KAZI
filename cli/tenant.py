"""kazi tenant — tenant management commands."""
import shutil
import sys
from pathlib import Path


def handle_tenant(args) -> None:
    """Dispatch tenant subcommands."""
    if args.tenant_command == "add":
        add_tenant(args.org_id, args.domain)
    elif args.tenant_command == "list":
        list_tenants()
    elif args.tenant_command == "validate":
        validate_tenant(args.file)
    elif args.tenant_command == "remove":
        remove_tenant(args.org_id)
    else:
        print("  Usage: kazi tenant {add|list|validate|remove}")
        sys.exit(1)


def add_tenant(org_id: str, domain: str) -> None:
    """Create a new tenant config from template."""
    tenants_dir = Path("./tenants")
    tenants_dir.mkdir(exist_ok=True)

    target = tenants_dir / f"{org_id}.yaml"
    if target.exists():
        print(f"\n  Error: Tenant '{org_id}' already exists at {target}")
        sys.exit(1)

    template = tenants_dir / "_template.yaml"
    if template.exists():
        shutil.copy(template, target)
    else:
        # Generate minimal tenant config
        content = f"""# Tenant: {org_id}
# Domain: {domain}
# Created by: kazi tenant add

org_id: "{org_id}"
name: "{org_id.replace('-', ' ').title()}"
domain: "{domain}"

destinations:
  review:
    adapter: webhook
    config:
      url: "https://example.com/webhook/review"

  publish:
    adapter: webhook
    config:
      url: "https://example.com/webhook/publish"

preferences:
  timezone: "UTC"
  schedule: "0 9 * * 1-5"
  auto_approve: false

secrets:
  # Reference environment variables with ${{ENV_VAR}} syntax
  # api_token: "${{ORG_ID_API_TOKEN}}"
"""
        target.write_text(content)

    print(f"\n  Tenant created: {target}")
    print(f"  Edit this file to configure destinations and secrets.")
    print()


def list_tenants() -> None:
    """List all configured tenants."""
    from kazi.platform.tenant import load_all_tenants

    tenants_dir = Path("./tenants")
    if not tenants_dir.exists():
        print("\n  No tenants/ directory found.")
        return

    tenants = load_all_tenants(tenants_dir)
    if not tenants:
        print("\n  No tenants configured.")
        print("  Create one with: kazi tenant add <org-id> --domain <domain>")
        return

    print(f"\n  Configured tenants ({len(tenants)}):")
    print(f"  {'ORG ID':<25} {'NAME':<30} {'DOMAIN':<15} {'DESTINATIONS'}")
    print(f"  {'─'*25} {'─'*30} {'─'*15} {'─'*20}")

    for t in tenants:
        dest_count = len(t.destinations) if hasattr(t, 'destinations') else 0
        print(f"  {t.org_id:<25} {t.name:<30} {t.domain:<15} {dest_count} configured")

    print()


def validate_tenant(file_path: str) -> None:
    """Validate a tenant config file."""
    import yaml
    from kazi.utils.validation import validate_tenant_config

    path = Path(file_path)
    if not path.exists():
        print(f"\n  Error: File not found: {path}")
        sys.exit(1)

    with open(path) as f:
        config = yaml.safe_load(f)

    result = validate_tenant_config(config)

    if result.valid:
        print(f"\n  ✓ Tenant config is valid: {path}")
    else:
        print(f"\n  ✗ Tenant config has errors:")
        for err in result.errors:
            print(f"    • {err}")

    if result.warnings:
        print(f"\n  Warnings:")
        for warn in result.warnings:
            print(f"    • {warn}")

    print()


def remove_tenant(org_id: str) -> None:
    """Remove a tenant config."""
    tenants_dir = Path("./tenants")
    target = tenants_dir / f"{org_id}.yaml"

    if not target.exists():
        print(f"\n  Error: Tenant '{org_id}' not found at {target}")
        sys.exit(1)

    target.unlink()
    print(f"\n  Tenant '{org_id}' removed.")
    print()
