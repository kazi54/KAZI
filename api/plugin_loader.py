"""Plugin Loader v2 — auto-discovers domain plugins and wires the full system.

Each domain must be a directory under ./domains/ containing:
- manifest.yaml — metadata, pipeline definitions, scoring, dashboard pages
- routes.py — FastAPI router with a `router` attribute
- agents/ — directory of BaseAgent subclasses (auto-discovered)
- scoring.yaml — optional scoring configuration

The loader now performs the full manifest-to-instance pipeline:
1. Discover agents (AgentRegistry)
2. Build pipelines from manifest (PipelineBuilder)
3. Register pipelines + triggers with Orchestrator
4. Mount API routes
5. Load tenant configs
6. Wire destination registry

Directories starting with '_' are skipped (e.g., _template/).
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from kazi.agents.registry import AgentRegistry
from kazi.delivery.destinations import DestinationRegistry
from kazi.orchestrator.builder import PipelineBuilder
from kazi.orchestrator.orchestrator import Orchestrator
from kazi.platform.tenant import TenantConfig, load_all_tenants


@dataclass
class LoadedDomain:
    """Metadata about a successfully loaded domain plugin."""

    name: str
    display_name: str
    version: str
    prefix: str
    path: Path
    agents: list[str] = field(default_factory=list)
    pipelines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PlatformState:
    """Runtime state of the fully loaded platform.

    Attached to `app.state.platform` for access by routes and middleware.
    """

    domains: list[LoadedDomain] = field(default_factory=list)
    agent_registry: AgentRegistry = field(default_factory=AgentRegistry)
    orchestrator: Orchestrator = field(default_factory=Orchestrator)
    destination_registry: DestinationRegistry = field(default_factory=DestinationRegistry)
    tenants: dict[str, TenantConfig] = field(default_factory=dict)


def load_platform(
    app: FastAPI,
    domains_dir: Path | str = "./domains",
    tenants_dir: Path | str = "./tenants",
) -> PlatformState:
    """Discover and wire the full KAZI OS platform.

    This is the single entry point that replaces the old `load_domains`.
    It performs the complete bootstrap sequence:

    1. Create shared registries (agents, destinations, orchestrator)
    2. For each domain:
       a. Discover agents from agents/ directory
       b. Build pipelines from manifest.yaml
       c. Register pipelines + triggers with orchestrator
       d. Mount FastAPI routes
    3. Load tenant configs from tenants/ directory
    4. Attach everything to app.state

    Args:
        app: The FastAPI application instance.
        domains_dir: Path to the domains directory (default: ./domains).
        tenants_dir: Path to the tenants directory (default: ./tenants).

    Returns:
        PlatformState with all loaded components.
    """
    domains_path = Path(domains_dir).resolve()
    tenants_path = Path(tenants_dir).resolve()

    state = PlatformState()

    print("╔══════════════════════════════════════════╗")
    print("║         KAZI OS — Platform Boot          ║")
    print("╚══════════════════════════════════════════╝")
    print()

    # ─── Phase 1: Discover Agents ─────────────────────────────────────────────
    print("─── Phase 1: Agent Discovery ───")
    if domains_path.exists():
        discovered = state.agent_registry.discover_all_domains(domains_path)
        total_agents = sum(len(v) for v in discovered.values())
        print(f"  Total agents discovered: {total_agents}")
    else:
        print(f"  ⚠ Domains directory not found: {domains_path}")
    print()

    # ─── Phase 2: Load Domains ────────────────────────────────────────────────
    print("─── Phase 2: Domain Loading ───")
    if not domains_path.exists():
        print(f"  ⚠ Domains directory not found: {domains_path}")
        return state

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

        domain = _load_single_domain(
            app=app,
            domain_path=domain_path,
            manifest_file=manifest_file,
            agent_registry=state.agent_registry,
            orchestrator=state.orchestrator,
        )
        state.domains.append(domain)

    print()

    # ─── Phase 3: Load Tenants ────────────────────────────────────────────────
    print("─── Phase 3: Tenant Loading ───")
    if tenants_path.exists():
        tenant_configs = load_all_tenants(tenants_path)
        for tc in tenant_configs:
            state.tenants[tc.org_id] = tc
            print(f"  ✓ Loaded tenant: {tc.name} ({tc.org_id}) → domain: {tc.domain}")
        if not tenant_configs:
            print("  (no tenant configs found)")
    else:
        print(f"  ℹ Tenants directory not found: {tenants_path} (optional)")
    print()

    # ─── Phase 4: Summary ─────────────────────────────────────────────────────
    print("─── Platform Summary ───")
    print(f"  Domains:    {len(state.domains)}")
    print(f"  Agents:     {state.agent_registry.count}")
    print(f"  Pipelines:  {len(state.orchestrator.pipelines)}")
    print(f"  Triggers:   {len(state.orchestrator.triggers)}")
    print(f"  Tenants:    {len(state.tenants)}")
    print(f"  Adapters:   {state.destination_registry.available_adapters}")
    print()

    # Attach to app state
    app.state.platform = state

    return state


def _load_single_domain(
    app: FastAPI,
    domain_path: Path,
    manifest_file: Path,
    agent_registry: AgentRegistry,
    orchestrator: Orchestrator,
) -> LoadedDomain:
    """Load a single domain: routes + pipelines + triggers."""
    manifest = yaml.safe_load(manifest_file.read_text())

    # Handle both flat and nested manifest formats
    domain_meta = manifest.get("domain", manifest)
    name = domain_meta.get("name", domain_path.name)
    display_name = domain_meta.get("display_name", name)
    version = domain_meta.get("version", "0.0.0")

    # Determine route prefix
    routes_config = manifest.get("routes", {})
    if isinstance(routes_config, dict):
        prefix = routes_config.get("prefix", f"/api/{name}")
    else:
        prefix = manifest.get("routes_prefix", f"/api/{name}")

    # Ensure prefix starts with /api if not already
    if not prefix.startswith("/api"):
        prefix = f"/api{prefix}"

    domain = LoadedDomain(
        name=name,
        display_name=display_name,
        version=version,
        prefix=prefix,
        path=domain_path,
    )

    # ── Mount Routes ──
    try:
        routes_module = importlib.import_module(f"domains.{domain_path.name}.routes")
        app.include_router(routes_module.router, prefix=prefix, tags=[display_name])
    except Exception as e:
        domain.errors.append(f"Routes: {e}")
        print(f"  ⚠ {name}: failed to mount routes: {e}")

    # ── Get domain agents ──
    domain_agents = agent_registry.get_domain_agents(domain_path.name)
    domain.agents = list(domain_agents.keys())

    # ── Build Pipelines ──
    if "pipelines" in manifest and domain_agents:
        builder = PipelineBuilder(agent_registry=domain_agents)
        result = builder.from_manifest(manifest)

        for pipeline in result.pipelines:
            orchestrator.register_pipeline(pipeline)
            domain.pipelines.append(pipeline.name)

        for trigger in result.triggers:
            orchestrator.register_trigger(trigger)

        if result.errors:
            domain.errors.extend(result.errors)
            for err in result.errors:
                print(f"  ⚠ {name}: {err}")

    # ── Report ──
    status = "✓" if not domain.errors else "⚠"
    print(
        f"  {status} {display_name} v{version} → {prefix} "
        f"(agents: {len(domain.agents)}, pipelines: {len(domain.pipelines)})"
    )

    return domain


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy API (backwards compatible)
# ═══════════════════════════════════════════════════════════════════════════════


def load_domains(
    app: FastAPI,
    domains_dir: Path | str = "./domains",
) -> list[LoadedDomain]:
    """Legacy entry point — wraps load_platform for backwards compatibility.

    Prefer `load_platform()` for new code.
    """
    state = load_platform(app, domains_dir=domains_dir)
    return state.domains


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
        domain_meta = manifest.get("domain", manifest)
        domain_name = domain_meta.get("name", domain_path.name)

        # Handle both formats: manifest.dashboard.pages and manifest.dashboard_pages
        dashboard = manifest.get("dashboard", {})
        if isinstance(dashboard, dict):
            page_list = dashboard.get("pages", [])
        else:
            page_list = manifest.get("dashboard_pages", [])

        for page in page_list:
            pages.append({**page, "domain": domain_name})

    return pages
