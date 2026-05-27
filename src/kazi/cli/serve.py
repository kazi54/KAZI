"""kazi serve — start the KAZI platform server."""
from pathlib import Path


def serve(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    workers: int = 1,
) -> None:
    """Start the KAZI FastAPI server with all domain plugins loaded."""
    import uvicorn
    from fastapi import FastAPI
    from api.plugin_loader import load_platform

    app = FastAPI(
        title="KAZI OS",
        description="Domain-agnostic platform for AI-powered professional services",
        version="0.3.0",
    )

    # Load platform (domains, agents, pipelines, tenants)
    print("\n  KAZI OS v0.3.0")
    print("  Loading platform...")

    platform = load_platform(
        app,
        domains_dir=Path("./domains"),
        tenants_dir=Path("./tenants"),
    )

    if not platform.get("domains"):
        print("  ⚠ No domains loaded. Create one with: kazi init <name>")

    tenant_count = len(platform.get("tenants", []))
    pipeline_count = len(platform.get("pipelines", []))
    print(f"  Domains:     {len(platform.get('domains', []))}")
    print(f"  Pipelines:   {pipeline_count}")
    print(f"  Tenants:     {tenant_count}")
    print()

    # Platform health endpoint
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.3.0",
            "domains": platform.get("domain_names", []),
            "tenants": tenant_count,
            "pipelines": pipeline_count,
        }

    # Domain registry endpoint
    @app.get("/api/domains")
    async def get_domains():
        return platform.get("domain_info", [])

    # Tenant registry endpoint
    @app.get("/api/tenants")
    async def get_tenants():
        return [
            {"org_id": t.org_id, "name": t.name, "domain": t.domain}
            for t in platform.get("tenants", [])
        ]

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


def list_domains() -> None:
    """List all available domain plugins."""
    from api.plugin_loader import load_domains
    from fastapi import FastAPI

    app = FastAPI()
    domains = load_domains(app, domains_dir=Path("./domains"))

    if not domains:
        print("  No domains found. Create one with: kazi init <name>")
        return

    print("\n  Loaded domains:")
    for d in domains:
        print(f"    • {d.display_name} v{d.version} → {d.prefix}")
    print()
