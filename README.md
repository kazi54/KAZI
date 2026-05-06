# KAZI

KAZI is a harness framework for professional services agents. Define your guides (scoring rubrics, templates, pipeline structure) and sensors (validation, scoring, human review) — KAZI orchestrates the rest.

**The open-source platform for building AI-powered professional services products.**

Define your agents, scoring rubrics, and report templates — KAZI handles orchestration, human review, and delivery.

---

## What is KAZI?

KAZI is a Python framework for building autonomous intelligence systems powered by multi-agent orchestration. It provides:

- **Agent orchestration** — Define pipelines of specialized agents (Scout → Score → Compile → Deliver)
- **Scoring engine** — Pluggable multi-dimensional scoring with configurable tiers
- **Template renderer** — Jinja2 → HTML → PDF report generation
- **Human-in-the-loop** — Review queues with approval workflows
- **Monitoring** — Scheduled re-evaluation with drift detection
- **Dashboard** — React shell with plugin-based page loading
- **CLI** — `kazi init`, `kazi run`, `kazi serve`

## Who is this for?

Thought leaders, domain experts, and consultants who want to turn their expertise into scalable AI-powered products — without building infrastructure from scratch.

**You bring:** Domain knowledge (scoring rubrics, agent prompts, report templates)  
**KAZI provides:** The engine (orchestration, delivery, monitoring, dashboard)

---

## Quickstart

```bash
# Install
pip install kazi

# Create a new domain
kazi init my-domain

# Define your agents in domains/my-domain/agents/
# Define your scoring in domains/my-domain/scoring.yaml
# Define your templates in domains/my-domain/templates/

# Run the platform
kazi serve
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   KAZI Platform                   │
├─────────────────────────────────────────────────┤
│  Orchestrator  │  Scoring  │  Templates  │ HITL │
├─────────────────────────────────────────────────┤
│              Plugin Loader (manifest.yaml)        │
├──────────┬──────────┬──────────┬────────────────┤
│ Domain A │ Domain B │ Domain C │    ...         │
│ (agents) │ (agents) │ (agents) │                │
└──────────┴──────────┴──────────┴────────────────┘
```

Each domain is a self-contained plugin with:
- `manifest.yaml` — metadata + route registration
- `agents/` — domain-specific agent implementations
- `scoring.yaml` — dimensions, weights, thresholds
- `templates/` — report HTML templates
- `routes.py` — FastAPI router (auto-mounted)
- `dashboard/` — React pages (auto-loaded)

## Core Abstractions

| Abstraction | Purpose |
|-------------|---------|
| `BaseAgent` | Unit of work — answers one question, produces structured output |
| `Pipeline` | Sequential chain — output of agent N feeds input of agent N+1 |
| `FanOut` | Parallel execution — same pipeline across N inputs |
| `Orchestrator` | Coordinator — dispatches jobs, manages triggers |
| `ScoreLegend` | Configurable scoring tiers (e.g., 0-40 = Abandon, 80-100 = Fast-track) |
| `ReviewQueue` | Human-in-the-loop — queue outputs for approval before delivery |

## Examples

See [`examples/`](./examples/) for working code:
- `hello_agent.py` — Your first agent in 10 lines
- `scout_score_pipeline.py` — Two-agent pipeline with scoring
- `weekly_brief.py` — Scheduled delivery with FanOut

## Documentation

- [Getting Started](./docs/getting-started.md)
- [Architecture](./docs/architecture.md)
- [Design Patterns](./docs/patterns.md)
- [Building Agents](./docs/agents.md)
- [Scoring System](./docs/scoring.md)
- [Templates](./docs/templates.md)
- [Plugins](./docs/plugins.md)

## License

Apache 2.0 — see [LICENSE](./LICENSE)

## Built with KAZI

- **insightbydrjean** — AI-powered thought leadership

---

*KAZI means "work" in Swahili.*
