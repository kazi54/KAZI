"""kazi init — scaffold a new domain plugin."""

import shutil
from pathlib import Path


def init_domain(domain_name: str) -> None:
    """Create a new domain plugin from the template."""
    domains_dir = Path("./domains")
    template_dir = domains_dir / "_template"
    target_dir = domains_dir / domain_name

    if target_dir.exists():
        print(f"  ✗ Domain '{domain_name}' already exists at {target_dir}")
        return

    if not template_dir.exists():
        print(f"  ✗ Template directory not found at {template_dir}")
        return

    # Copy template
    shutil.copytree(template_dir, target_dir)

    # Update manifest with the new domain name
    manifest_path = target_dir / "manifest.yaml"
    content = manifest_path.read_text()
    content = content.replace("my-domain", domain_name)
    content = content.replace("My Domain", domain_name.replace("-", " ").title())
    content = content.replace("MyDomain", domain_name.replace("-", "").title())
    manifest_path.write_text(content)

    # Update routes.py
    routes_path = target_dir / "routes.py"
    content = routes_path.read_text()
    content = content.replace("my-domain", domain_name)
    routes_path.write_text(content)

    print(f"  ✓ Created domain: {domain_name}")
    print(f"    → {target_dir}/")
    print()
    print("  Next steps:")
    print(f"    1. Edit {target_dir}/manifest.yaml")
    print(f"    2. Add agents to {target_dir}/agents/")
    print(f"    3. Configure {target_dir}/scoring.yaml")
    print(f"    4. Add templates to {target_dir}/templates/")
    print(f"    5. Run: kazi serve")
