"""kazi init — scaffold a new domain plugin."""

import shutil
from pathlib import Path
from importlib import resources


def _find_template_dir() -> Path | None:
    """Locate the domain template directory.
    
    Checks in order:
    1. ./domains/_template (local project)
    2. Bundled with the kazi package
    """
    local = Path("./domains/_template")
    if local.exists():
        return local

    # Fallback: bundled template inside the installed package
    try:
        pkg_root = Path(resources.files("kazi")).parent  # type: ignore
        bundled = pkg_root / "kazi" / "domains" / "_template"
        if bundled.exists():
            return bundled
    except Exception:
        pass

    return None


def init_domain(domain_name: str, with_scoring: bool = False) -> None:
    """Create a new domain plugin from the template."""
    target_dir = Path(domain_name)

    if target_dir.exists():
        print(f"  ✗ Directory '{domain_name}' already exists")
        return

    template_dir = _find_template_dir()
    if template_dir is None:
        # Create a minimal scaffold if no template is found
        _create_minimal_scaffold(target_dir, domain_name, with_scoring)
        return

    # Copy template
    shutil.copytree(template_dir, target_dir)

    # Update manifest with the new domain name
    manifest_path = target_dir / "manifest.yaml"
    if manifest_path.exists():
        content = manifest_path.read_text()
        content = content.replace("my-domain", domain_name)
        content = content.replace("My Domain", domain_name.replace("-", " ").title())
        content = content.replace("MyDomain", domain_name.replace("-", "").title())
        manifest_path.write_text(content)

    # Update routes.py
    routes_path = target_dir / "routes.py"
    if routes_path.exists():
        content = routes_path.read_text()
        content = content.replace("my-domain", domain_name)
        routes_path.write_text(content)

    # Remove scoring.yaml if not requested
    if not with_scoring:
        scoring_path = target_dir / "scoring.yaml"
        if scoring_path.exists():
            scoring_path.unlink()

    _print_success(domain_name, target_dir)


def _create_minimal_scaffold(target_dir: Path, domain_name: str, with_scoring: bool) -> None:
    """Create a minimal domain scaffold without a template."""
    target_dir.mkdir(parents=True)
    (target_dir / "agents").mkdir()
    (target_dir / "templates").mkdir()

    # manifest.yaml
    title = domain_name.replace("-", " ").title()
    manifest = f"""# {title} Domain Manifest
domain: {domain_name}
version: "0.1.0"
description: "{title} domain plugin"

agents: []

pipelines: []

triggers: []
"""
    (target_dir / "manifest.yaml").write_text(manifest)

    # scoring.yaml (optional)
    if with_scoring:
        scoring = f"""# {title} Scoring Configuration
dimensions: []
legend:
  - label: "High"
    min: 80
    max: 100
  - label: "Medium"
    min: 50
    max: 79
  - label: "Low"
    min: 0
    max: 49
"""
        (target_dir / "scoring.yaml").write_text(scoring)

    # README
    readme = f"""# {title}

A KAZI OS domain plugin.

## Getting Started

1. Define your agents in `agents/`
2. Configure pipelines in `manifest.yaml`
3. Add report templates in `templates/`
4. Run: `kazi serve`
"""
    (target_dir / "README.md").write_text(readme)

    _print_success(domain_name, target_dir)


def _print_success(domain_name: str, target_dir: Path) -> None:
    """Print success message and next steps."""
    print(f"\n  ✓ Created domain: {domain_name}")
    print(f"    → {target_dir}/")
    print()
    print("  Next steps:")
    print(f"    1. Edit {target_dir}/manifest.yaml")
    print(f"    2. Add agents to {target_dir}/agents/")
    print(f"    3. Add templates to {target_dir}/templates/")
    print(f"    4. Run: kazi serve")
