# Plugins (Domain System)

A **domain plugin** is a self-contained package that adds a complete product vertical to KAZI OS. Each domain defines its own agents, scoring rubrics, templates, routes, and dashboard pages. The platform discovers and loads domains automatically at startup.

---

## What is a Domain?

A domain represents one professional services product built on KAZI OS. Examples:

| Domain | Product | What it does |
|--------|---------|--------------|
| `carta` | CARTA | Patent commercialization analysis |
| `rfi` | Research Funding Intelligence | Grant/funding opportunity matching |
| `insight` | insightbydrjean | Thought leadership content production |

Each domain is a separate repository that plugs into the KAZI OS platform via a standard interface.

---

## Domain Structure

Every domain follows this directory layout:

```
kazi-{domain}/
├── manifest.yaml          # Required — domain configuration
├── routes.py              # Required — FastAPI router
├── agents/                # Domain-specific agents
│   ├── __init__.py
│   ├── scout.py
│   ├── scorer.py
│   └── compiler.py
├── scoring.yaml           # Scoring dimensions, weights, legend
├── templates/             # Report/deliverable templates
│   ├── report_v2.html
│   └── _partials/
├── schemas/               # Database migrations (SQL)
│   └── 001_initial.sql
├── dashboard/             # Frontend components (optional)
│   └── pages/
├── data_sources/          # External API integrations
├── tests/
├── README.md
└── .gitignore
```

---

## The Manifest

The `manifest.yaml` is the single source of truth for a domain's configuration. The plugin loader reads this file to register the domain with the platform.

```yaml
# manifest.yaml

domain:
  name: carta
  display_name: "CARTA"
  description: "Patent commercialization analysis and licensing intelligence"
  version: "2.0.0"
  author: "KAZI54"

# Pipeline definitions
pipelines:
  full_audit:
    description: "Complete patent audit (9 sections)"
    stages:
      - agent: patent_scout
        required: true
      - agent: market_scout
        required: true
      - agent: inventor_profiler
        required: false
      - agent: commercial_scorer
        required: true
      - agent: licensee_finder
        required: true
      - agent: report_compiler
        required: true
    trigger:
      type: on_demand
    delivery:
      template: audit_report_v2.html
      format: [html, pdf]

  monitoring:
    description: "Monthly re-evaluation of delivered reports"
    stages:
      - agent: drift_detector
        required: true
      - agent: re_scorer
        required: true
    trigger:
      type: scheduled
      cron: "0 2 1 * *"    # First of every month at 2 AM

# Scoring configuration reference
scoring: scoring.yaml

# API routes
routes:
  prefix: /carta
  module: routes

# Dashboard pages
dashboard:
  pages:
    - id: home
      title: "Home"
      path: /carta
    - id: engagements
      title: "Engagements"
      path: /carta/engagements
    - id: revenue
      title: "Revenue"
      path: /carta/revenue

# HITL configuration
hitl:
  policy: always
  reviewers:
    - role: domain_expert
  sections_requiring_review:
    - strategy_memo
    - executive_summary

# Custom tools this domain needs
tools:
  - name: uspto_api
    module: data_sources.uspto
  - name: google_patents
    module: data_sources.google_patents

# Database schema
database:
  schema: carta
  migrations: schemas/
```

---

## Plugin Loader

The platform's plugin loader (`api/plugin_loader.py`) discovers and registers domains at startup. It performs the following steps:

1. **Scan** — looks for `manifest.yaml` files in the `domains/` directory
2. **Validate** — checks that required fields are present and well-formed
3. **Register routes** — mounts the domain's FastAPI router at the configured prefix
4. **Register agents** — adds agents to the platform's agent registry
5. **Register pipelines** — makes pipelines available to the orchestrator
6. **Register dashboard pages** — exposes dashboard page metadata to the frontend

```python
# Simplified plugin loader logic
from pathlib import Path
import yaml

def load_domains(app, domains_dir: Path):
    """Discover and register all domain plugins."""
    for manifest_path in domains_dir.glob("*/manifest.yaml"):
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
        
        domain_name = manifest["domain"]["name"]
        domain_dir = manifest_path.parent
        
        # Mount routes
        routes_module = import_module(domain_dir / manifest["routes"]["module"])
        app.include_router(
            routes_module.router,
            prefix=f"/api{manifest['routes']['prefix']}",
            tags=[domain_name],
        )
        
        # Register with platform
        app.state.domains[domain_name] = manifest
```

---

## Creating a New Domain

### Step 1: Initialize from Template

```bash
kazi init my-domain
# Creates: domains/my-domain/ with all required files
```

Or manually copy the template:

```bash
cp -r domains/_template domains/my-domain
```

### Step 2: Define the Manifest

Edit `manifest.yaml` with your domain's configuration:
- Name and description
- Pipeline stages (which agents, in what order)
- Scoring dimensions and legend
- Trigger types (on-demand, scheduled, event-driven)
- Dashboard pages

### Step 3: Write Agents

Create agents in the `agents/` directory. Each agent extends one of the base classes:

```python
# agents/my_scout.py
from kazi.agents import BaseScoutAgent

class MyScout(BaseScoutAgent):
    name = "my_scout"
    description = "Discovers relevant data for this domain"

    async def run(self, input_data: dict) -> dict:
        # Your domain-specific logic
        return {"findings": [...]}
```

### Step 4: Define Scoring

Create `scoring.yaml` with dimensions, weights, and legend appropriate to your domain.

### Step 5: Build Templates

Create HTML templates in `templates/` for your deliverables.

### Step 6: Define Routes

Write the FastAPI router in `routes.py`:

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "domain": "my-domain"}

@router.post("/jobs")
async def create_job(payload: dict):
    # Trigger a pipeline execution
    ...

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    # Return job status and results
    ...
```

### Step 7: Test

```bash
cd domains/my-domain
pytest tests/
```

### Step 8: Register

Symlink or install the domain into the platform's `domains/` directory:

```bash
# Development (symlink)
ln -s /path/to/kazi-my-domain /path/to/kazi/domains/my-domain

# Production (pip install)
pip install -e /path/to/kazi-my-domain
```

Restart the server. The plugin loader will discover and register the new domain automatically.

---

## Domain Isolation

Domains are isolated from each other:

| Boundary | Enforcement |
|----------|-------------|
| Database | Separate PostgreSQL schemas (`carta.*`, `rfi.*`, `insight.*`) |
| Routes | Separate API prefixes (`/api/carta/`, `/api/rfi/`, `/api/insight/`) |
| Agents | Registered under domain namespace |
| Templates | Stored in domain's own `templates/` directory |
| Config | Each domain has its own `manifest.yaml` and `scoring.yaml` |

Domains cannot directly access each other's data or agents. If cross-domain communication is needed, it goes through the platform's orchestrator.

---

## Domain Lifecycle

```
Development → Testing → Staging → Production
```

| Phase | What happens |
|-------|-------------|
| Development | Domain runs locally via `kazi serve` with symlinked directory |
| Testing | Automated tests run against mock data and mocked tools |
| Staging | Domain deployed to staging environment with real data sources |
| Production | Domain active in production, serving real clients |

### Versioning

Domains use semantic versioning in their `manifest.yaml`:

```yaml
domain:
  version: "2.1.0"   # major.minor.patch
```

- **Major** — breaking changes to output schema or API contract
- **Minor** — new features, new agents, new template versions
- **Patch** — bug fixes, prompt improvements, scoring adjustments

---

## Inter-Domain Communication

In rare cases, domains may need to reference each other's outputs (e.g., CARTA needs inventor data that RFI already has). This is handled through the platform's shared data layer:

```python
# Access another domain's data via platform API (not direct import)
from kazi.platform import data_bridge

inventor_profile = await data_bridge.query(
    domain="rfi",
    entity="researcher_profiles",
    filter={"name": "Dr. Sarah Chen"},
)
```

This maintains isolation while enabling controlled data sharing. The `data_bridge` respects RLS policies and requires explicit permissions in the manifest:

```yaml
# manifest.yaml
permissions:
  read_from:
    - domain: rfi
      entities: [researcher_profiles]
```

---

## Deployment Topology

### Local Development

```
kazi/
├── domains/
│   ├── carta → symlink to ../kazi-carta
│   ├── rfi → symlink to ../kazi-rfi
│   └── insight → symlink to ../kazi-insight
```

### Docker Production

```yaml
# docker-compose.yml
services:
  kazi:
    build: ./kazi
    volumes:
      - ./kazi-carta:/app/domains/carta
      - ./kazi-rfi:/app/domains/rfi
      - ./kazi-insight:/app/domains/insight
    environment:
      - SUPABASE_URL=...
      - SUPABASE_KEY=...
```

### pip Install (for community users)

```bash
pip install kazi
pip install kazi-my-domain    # If published to PyPI

# Or from git
pip install git+https://github.com/my-org/kazi-my-domain.git
```

---

## Checklist: Domain Ready for Production

| Check | Status |
|-------|--------|
| `manifest.yaml` is complete and valid | |
| All agents have unit tests | |
| Scoring rubric tested with 5+ real items | |
| Templates render correctly (HTML + PDF) | |
| Routes respond to health check | |
| Database migrations run cleanly | |
| HITL workflow tested end-to-end | |
| No hardcoded secrets | |
| README documents setup and usage | |
| Version number set appropriately | |
