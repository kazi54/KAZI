"""kazi serve — start the KAZI platform server."""

from pathlib import Path


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the KAZI FastAPI server with all domain plugins loaded."""
    import uvicorn
    from fastapi import FastAPI
    from api.plugin_loader import load_domains

    app = FastAPI(
        title="KAZI Platform",
        description="AI-powered professional services platform",
        version="0.1.0",
    )

    # Load domain plugins
    print("\n  KAZI Platform v0.1.0")
    print("  Loading domains...")
    domains = load_domains(app, domains_dir=Path("./domains"))

    if not domains:
        print("  ⚠ No domains loaded. Create one with: kazi init <name>")
    print()

    # Platform health endpoint
    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "domains": [d.name for d in domains],
        }

    # Domain registry endpoint (for frontend plugin loading)
    @app.get("/api/domains")
    async def get_domains():
        return [
            {
                "name": d.name,
                "display_name": d.display_name,
                "version": d.version,
                "prefix": d.prefix,
            }
            for d in domains
        ]

    uvicorn.run(app, host=host, port=port)


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
