"""KAZI platform — tenant management, configuration, auth."""
from kazi.platform.tenant import (
    TenantConfig,
    load_tenant,
    load_all_tenants,
)

__all__ = [
    "TenantConfig",
    "load_tenant",
    "load_all_tenants",
]
