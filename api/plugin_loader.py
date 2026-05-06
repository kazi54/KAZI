"""Plugin Loader — auto-discovers domain plugins and registers them with FastAPI.

Each domain must be a directory under ./domains/ containing:
- manifest.yaml — metadata (name, version, routes_prefix, dashboard_pages)
- routes.py — FastAPI router with a `router` attribute

Directories starting with '_' are skipped (e.g., _template/).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI


@dataclass
class LoadedDomain:
    """Metadata about a successfully loaded domain plugin."""

    name: str
    display_name: str
    version: str
    prefix: str
    path: Path


from dataclasses import dataclass


def load_domains(
    app: FastAPI,
    domains_dir: Path | str = "./domains",
) -> list[LoadedDomain]:
    """Discover and mount all domain plugins.

    Args:
        app: The FastAPI application instance
        domains_dir: Path to the domains directory (default: ./domains)

    Returns:
        List of successfully loaded domains
    """
    domains_path = Path(domains_dir).resolve()
    loaded: list[LoadedDomain] = []

    if not domains_path.exists():
        print(f"  ⚠ Domains directory not found: {domains_path}")
        return loaded

    # Add domains dir to sys.path for imports
    if str(domains_path.parent) not in sys.path:
        sys.path.insert(0, str(domains_path.parent))

    for domain_path in sorted(domains_path.iterdir()):
        # Skip non-directories and underscore-prefixed (templates, etc.)
        if not domain_path.is_dir() or domain_path.name.startswith("_"):
            continue

        manifest_file = domain_path / "manifest.yaml"
        if not manifest_file.exists():
            print(f"  ⚠ Skipping {domain_path.name}: no manifest.yaml")
            continue

        try:
            manifest = yaml.safe_load(manifest_file.read_text())
            name = manifest["name"]
            display_name = manifest.get("display_name", name)
            version = manifest.get("version", "0.0.0")
            prefix = manifest.get("routes_prefix", f"/api/{name}")
            tags = [display_name]

            # Import and mount routes
            routes_module = importlib.import_module(f"domains.{domain_path.name}.routes")
            app.include_router(routes_module.router, prefix=prefix, tags=tags)

            domain = LoadedDomain(
                name=name,
                display_name=display_name,
                version=version,
                prefix=prefix,
                path=domain_path,
            )
            loaded.append(domain)
            print(f"  ✓ Loaded domain: {display_name} v{version} → {prefix}")

        except Exception as e:
            print(f"  ✗ Failed to load {domain_path.name}: {e}")

    return loaded


def get_domain_dashboard_pages(domains_dir: Path | str = "./domains") -> list[dict[str, Any]]:
    """Extract dashboard page definitions from all domain manifests.

    Used by the frontend to dynamically register routes.

    Returns:
        List of page definitions: [{id, path, component, domain}]
    """
    domains_path = Path(domains_dir).resolve()
    pages: list[dict[str, Any]] = []

    if not domains_path.exists():
        return pages

    for domain_path in sorted(domains_path.iterdir()):
        if not domain_path.is_dir() or domain_path.name.startswith("_"):
            continue

        manifest_file = domain_path / "manifest.yaml"
        if not manifest_file.exists():
            continue

        manifest = yaml.safe_load(manifest_file.read_text())
        domain_name = manifest["name"]

        for page in manifest.get("dashboard_pages", []):
            pages.append({**page, "domain": domain_name})

    return pages
