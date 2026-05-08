# Getting Started

This guide takes you from zero to a running KAZI OS instance with a working agent in under 10 minutes.

---

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.11+ | Runtime |
| pip or uv | Latest | Package management |
| Docker (optional) | 24+ | Supabase local, containerized deployment |
| Node.js (optional) | 22+ | Dashboard frontend |

---

## Installation

### From PyPI

```bash
pip install kazi
```

### From Source (development)

```bash
git clone https://github.com/Jean-njoroge/KAZI.git
cd KAZI
pip install -e ".[dev]"
```

---

## Your First Agent

Create a file called `my_agent.py`:

```python
from kazi.agents import BaseAgent

class GreetingAgent(BaseAgent):
    """A minimal agent that greets a user by name."""

    name = "greeter"
    description = "Produces a personalized greeting"

    async def run(self, input_data: dict) -> dict:
        name = input_data.get("name", "World")
        return {
            "greeting": f"Hello, {name}! Welcome to KAZI OS.",
            "confidence": 1.0,
        }
```

Run it directly:

```bash
kazi run my_agent.py --input '{"name": "Dr. Jean"}'
```

Output:

```json
{
  "greeting": "Hello, Dr. Jean! Welcome to KAZI OS.",
  "confidence": 1.0
}
```

---

## Your First Domain

A domain is a self-contained product that runs on KAZI OS. Create one with the CLI:

```bash
kazi init my-domain
```

This generates:

```
domains/my-domain/
├── manifest.yaml       # Metadata, pipeline definition, triggers
├── agents/             # Your agent implementations
├── scoring.yaml        # Scoring dimensions and thresholds
├── templates/          # Report HTML templates
├── routes.py           # FastAPI router (auto-mounted at /api/my-domain/)
├── dashboard/          # React pages (auto-loaded)
└── README.md           # Domain documentation
```

### Define Your Pipeline

Edit `domains/my-domain/manifest.yaml`:

```yaml
name: my-domain
version: "0.1.0"
description: "My first KAZI domain"

pipeline:
  stages:
    - agent: scout
      class: agents.scout.ScoutAgent
    - agent: score
      class: agents.score.ScoreAgent
    - agent: compile
      class: agents.compile.CompileAgent

triggers:
  - type: on_demand
    route: /run
```

### Implement Your Agents

Each agent extends `BaseAgent` and implements the `run()` method. See [Building Agents](./building-agents.md) for the full API.

### Define Scoring

Edit `domains/my-domain/scoring.yaml`:

```yaml
dimensions:
  - name: relevance
    weight: 0.4
    description: "How relevant is this to the target domain?"
  - name: feasibility
    weight: 0.3
    description: "How feasible is the recommended action?"
  - name: impact
    weight: 0.3
    description: "What is the potential impact?"

legend:
  - range: [0, 40]
    tier: abandon
    label: "Abandon"
    color: "#ef4444"
    action: "Do not pursue"
  - range: [40, 60]
    tier: evaluate
    label: "Evaluate"
    color: "#f59e0b"
    action: "Needs further analysis"
  - range: [60, 80]
    tier: pursue
    label: "Pursue"
    color: "#22c55e"
    action: "Proceed with action"
  - range: [80, 100]
    tier: fast_track
    label: "Fast-track"
    color: "#06b6d4"
    action: "Immediate priority"
```

---

## Running the Platform

### Development Mode

```bash
kazi serve
```

This starts:
- FastAPI server on `http://localhost:8000`
- Auto-discovers all domains in `domains/`
- Mounts routes, loads scoring configs, registers pipelines
- Serves the dashboard at `http://localhost:3000` (if frontend is built)

### With Docker

```bash
docker compose up
```

The default `docker-compose.yml` includes:
- KAZI API server
- Supabase (PostgreSQL + Auth + Storage + Realtime)
- Dashboard frontend

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# LLM Provider
OPENAI_API_KEY=sk-...

# Supabase
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_KEY=your-service-key

# Platform
KAZI_ENV=development
KAZI_LOG_LEVEL=info
KAZI_DOMAINS_DIR=./domains
```

---

## Verify Installation

```bash
# Check CLI
kazi --version

# List registered domains
kazi domains

# Health check
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "domains": ["my-domain"],
  "agents_registered": 3
}
```

---

## Next Steps

| What | Where |
|------|-------|
| Understand the system architecture | [Architecture](./architecture.md) |
| Learn agent design patterns | [Design Patterns](./design-patterns.md) |
| Build production agents | [Building Agents](./building-agents.md) |
| Configure scoring rubrics | [Scoring System](./scoring-system.md) |
| Design report templates | [Templates](./templates.md) |
| Create a full domain plugin | [Plugins](./plugins.md) |
