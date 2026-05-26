"""Tenant Configuration — multi-tenant isolation via config, not code.

Each tenant is defined by a `tenant.yaml` file that declares:
- Identity (org_id, name)
- Destinations (where outputs go — CRM-agnostic)
- Secrets (resolved from environment variables)
- Preferences (schedule, delivery format, etc.)

KAZI OS is CRM-agnostic. Notion is an adapter, not the platform.
Salesforce is an adapter. Airtable is an adapter. The tenant declares
which adapters they use.

Usage:
    from kazi.platform.tenant import TenantConfig, load_tenant

    tenant = load_tenant("./tenants/silicon-xchange.yaml")
    print(tenant.org_id)           # "silicon-xchange"
    print(tenant.destinations)     # {"review": {...}, "publish": {...}}
    print(tenant.get_secret("NOTION_TOKEN"))  # resolved from env
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ═══════════════════════════════════════════════════════════════════════════════
# Core Data Structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TenantDestination:
    """A single destination configuration for a tenant.

    Attributes:
        key: Logical name (e.g., "review", "publish", "notify").
        adapter: Which adapter to use (e.g., "notion", "salesforce", "webhook").
        config: Adapter-specific settings (workspace IDs, URLs, etc.).
    """

    key: str
    adapter: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantConfig:
    """Complete tenant configuration.

    Loaded from a tenant.yaml file. Provides typed access to all
    tenant-specific settings needed by KAZI OS at runtime.

    Attributes:
        org_id: Unique identifier for this tenant. Used in AgentContext,
            database scoping, and log entries.
        name: Human-readable tenant name.
        domain: Which domain plugin this tenant uses (e.g., "content", "ip-intel").
        destinations: Map of logical destination keys to adapter configs.
        secrets: Resolved secret values (from env vars).
        preferences: Tenant-specific preferences (schedule, format, etc.).
        metadata: Any additional tenant metadata.
    """

    org_id: str
    name: str
    domain: str
    destinations: dict[str, TenantDestination] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_secret(self, key: str) -> str | None:
        """Get a resolved secret value by key."""
        return self.secrets.get(key)

    def get_destination(self, key: str) -> TenantDestination | None:
        """Get a destination config by logical key."""
        return self.destinations.get(key)

    def get_destinations_dict(self) -> dict[str, dict[str, Any]]:
        """Get destinations in the format expected by DestinationRegistry.resolve().

        Returns:
            Dict mapping destination key → {"adapter": str, "config": dict}
        """
        return {
            key: {"adapter": dest.adapter, "config": dest.config}
            for key, dest in self.destinations.items()
        }

    def to_agent_context_kwargs(self) -> dict[str, Any]:
        """Extract fields needed to construct an AgentContext for this tenant."""
        return {
            "org_id": self.org_id,
            "product": self.domain,
            "metadata": {
                "tenant_name": self.name,
                **self.metadata,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════════════


_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _resolve_secrets(raw: dict[str, str]) -> dict[str, str]:
    """Resolve secret values from environment variables.

    Supports ${VAR_NAME} syntax. If the env var is not set,
    the value remains as the raw string (allows for fallback detection).

    Example:
        raw = {"notion_token": "${NOTION_TOKEN}", "api_key": "${MY_API_KEY}"}
        resolved = _resolve_secrets(raw)
        # → {"notion_token": "actual-value-from-env", "api_key": "actual-value"}
    """
    resolved = {}
    for key, value in raw.items():
        if isinstance(value, str):
            match = _ENV_VAR_PATTERN.fullmatch(value)
            if match:
                env_var = match.group(1)
                env_value = os.environ.get(env_var)
                if env_value is not None:
                    resolved[key] = env_value
                else:
                    resolved[key] = value  # Keep raw — caller can detect unresolved
            else:
                resolved[key] = value
        else:
            resolved[key] = str(value)
    return resolved


def _resolve_config_secrets(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve ${ENV_VAR} references in a config dict.

    Walks the entire config tree and replaces any string matching
    ${VAR_NAME} with the corresponding environment variable value.
    """
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str):
            match = _ENV_VAR_PATTERN.fullmatch(value)
            if match:
                env_var = match.group(1)
                env_value = os.environ.get(env_var)
                resolved[key] = env_value if env_value is not None else value
            else:
                resolved[key] = value
        elif isinstance(value, dict):
            resolved[key] = _resolve_config_secrets(value)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_config_secrets(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def load_tenant(path: str | Path) -> TenantConfig:
    """Load and parse a tenant configuration file.

    Args:
        path: Path to the tenant.yaml file.

    Returns:
        A fully resolved TenantConfig instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required fields are missing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tenant config not found: {path}")

    raw = yaml.safe_load(path.read_text())

    # Validate required fields
    if not raw.get("org_id"):
        raise ValueError(f"Tenant config missing 'org_id': {path}")
    if not raw.get("domain"):
        raise ValueError(f"Tenant config missing 'domain': {path}")

    # Parse destinations
    destinations: dict[str, TenantDestination] = {}
    for key, dest_data in raw.get("destinations", {}).items():
        config = dest_data.get("config", {})
        # Resolve env vars in destination configs
        config = _resolve_config_secrets(config)
        destinations[key] = TenantDestination(
            key=key,
            adapter=dest_data["adapter"],
            config=config,
        )

    # Resolve secrets
    secrets = _resolve_secrets(raw.get("secrets", {}))

    return TenantConfig(
        org_id=raw["org_id"],
        name=raw.get("name", raw["org_id"]),
        domain=raw["domain"],
        destinations=destinations,
        secrets=secrets,
        preferences=raw.get("preferences", {}),
        metadata=raw.get("metadata", {}),
    )


def load_all_tenants(tenants_dir: str | Path) -> list[TenantConfig]:
    """Load all tenant configs from a directory.

    Scans for *.yaml and *.yml files in the given directory.

    Args:
        tenants_dir: Path to the tenants directory.

    Returns:
        List of loaded TenantConfig instances.
    """
    tenants_path = Path(tenants_dir)
    if not tenants_path.exists():
        return []

    tenants: list[TenantConfig] = []
    for config_file in sorted(tenants_path.glob("*.y*ml")):
        if config_file.name.startswith("_"):
            continue
        try:
            tenant = load_tenant(config_file)
            tenants.append(tenant)
        except Exception as e:
            print(f"  ⚠ Failed to load tenant {config_file.name}: {e}")

    return tenants
