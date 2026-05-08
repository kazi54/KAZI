# Architecture

This document describes the internal architecture of KAZI OS — how the platform is structured, how data flows through it, and how domain plugins integrate with the core.

---

## System Overview

KAZI OS is a **harness framework** for professional services agents. The term "harness" comes from Martin Fowler's concept of harness engineering for AI systems [1]: a combination of **feedforward guides** (scoring rubrics, templates, pipeline structure) and **feedback sensors** (validation, scoring, human review) that constrain and direct agent behavior.

The platform follows a layered architecture where the core provides orchestration, scoring, delivery, and monitoring capabilities, while domain plugins supply the domain-specific agents, rubrics, and templates.

```
┌─────────────────────────────────────────────────────────────────┐
│                         KAZI OS Platform                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────┐  ┌─────────┐  ┌───────────┐  ┌──────────────┐  │
│  │Orchestrator│  │ Scoring │  │ Templates │  │     HITL     │  │
│  └───────────┘  └─────────┘  └───────────┘  └──────────────┘  │
│                                                                   │
│  ┌───────────┐  ┌─────────┐  ┌───────────┐  ┌──────────────┐  │
│  │  Delivery │  │  State  │  │Monitoring │  │   Platform   │  │
│  └───────────┘  └─────────┘  └───────────┘  └──────────────┘  │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│                    Plugin Loader (manifest.yaml)                   │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   Domain A   │   Domain B   │   Domain C   │       ...          │
│   (agents,   │   (agents,   │   (agents,   │                    │
│    scoring,  │    scoring,  │    scoring,  │                    │
│    templates)│    templates)│    templates)│                    │
└──────────────┴──────────────┴──────────────┴────────────────────┘
```

---

## Core Modules

### Orchestrator (`src/kazi/orchestrator/`)

The orchestrator is the execution engine. It receives jobs, resolves which pipeline to run, dispatches agents in sequence or parallel, and manages job lifecycle.

| Component | Responsibility |
|-----------|---------------|
| `Orchestrator` | Top-level coordinator — accepts jobs, resolves pipelines, manages triggers |
| `Pipeline` | Sequential execution — output of stage N becomes input of stage N+1 |
| `FanOut` | Parallel execution — runs the same pipeline across N independent inputs |
| `Job` | Unit of execution — tracks state (pending → running → review → complete → failed) |
| `Trigger` | Initiates jobs — on-demand (API call), scheduled (cron), or event-driven (webhook/DB event) |

**Job lifecycle:**

```
pending → running → [review] → complete
                  ↘ failed
```

The `review` state is optional and only activates when the pipeline's HITL configuration requires human approval before delivery.

### Agents (`src/kazi/agents/`)

Agents are the atomic units of work. Each agent answers one question and produces structured output. The base class hierarchy provides specialized interfaces for common agent roles.

| Base Class | Role | Input | Output |
|-----------|------|-------|--------|
| `BaseAgent` | Generic agent | `dict` | `dict` |
| `BaseScoutAgent` | Discovery/research | Query parameters | List of findings |
| `BaseScoreAgent` | Evaluation/scoring | Item + rubric | Scored assessment |
| `BaseProfileAgent` | Entity profiling | Entity identifier | Structured profile |
| `BaseCompileAgent` | Report assembly | Scored data + template | Rendered document |

Every agent implements a single `async run(input_data: dict) -> dict` method. Agents are stateless — all state lives in the job context passed between pipeline stages.

### Scoring (`src/kazi/scoring/`)

The scoring engine provides a configurable multi-dimensional evaluation system. Domains define their own scoring dimensions, weights, and tier thresholds.

| Component | Responsibility |
|-----------|---------------|
| `ScoringDimension` | One axis of evaluation (name, weight, description, scoring function) |
| `ScoringSystem` | Collection of dimensions — computes weighted composite score |
| `ScoreLegend` | Maps numeric scores to actionable tiers (Abandon / Evaluate / Pursue / Fast-track) |
| `ScoreTier` | One tier definition (range, label, color, recommended action) |

The scoring system is **domain-agnostic** — the platform provides the engine, domains provide the rubrics via `scoring.yaml`.

### Templates (`src/kazi/delivery/`)

The template renderer converts structured data into formatted deliverables (HTML reports, PDF documents, email briefs). It uses Jinja2 for templating with support for:

- Section-based report structure
- Print/PDF page breaks
- Score visualization (colored dots, rings, bars)
- HITL markers (human-written vs. AI-generated sections)
- Variable interpolation from pipeline output

### HITL (`src/kazi/hitl/`)

The human-in-the-loop module manages review queues. When a pipeline stage or final output requires human approval, the job enters the `review` state and appears in the review queue.

| Component | Responsibility |
|-----------|---------------|
| `ReviewQueue` | Ordered list of items awaiting human review |
| `ReviewItem` | One item — includes the output, context, and approval/rejection interface |
| `ReviewPolicy` | Rules for when HITL is required (always, above threshold, random sample) |

### State (`src/kazi/state/`)

The state module manages persistent storage of jobs, scores, and domain data. It abstracts the database layer so domains don't couple to a specific database provider.

| Component | Responsibility |
|-----------|---------------|
| `JobStore` | CRUD for jobs (create, read, update status, query by domain/status) |
| `ScoreStore` | Historical score storage for drift detection |
| `DomainStore` | Domain-specific data (engagements, profiles, etc.) |

The default implementation uses Supabase (PostgreSQL + Row-Level Security), but the interface is abstract — domains can swap in any storage backend.

### Monitoring (`src/kazi/platform/`)

The monitoring module handles scheduled re-evaluation. It detects when previously scored items may have drifted (new data available, market changes, time decay) and triggers re-assessment pipelines.

| Component | Responsibility |
|-----------|---------------|
| `MonitoringScheduler` | Cron-based job scheduler for periodic re-evaluation |
| `DriftDetector` | Compares current score to historical baseline, flags significant changes |
| `AlertDispatcher` | Notifies stakeholders when drift exceeds threshold |

---

## Data Flow

A typical request flows through the system as follows:

```
1. Trigger fires (API call, cron, event)
         │
2. Orchestrator creates Job
         │
3. Pipeline resolves stages from manifest.yaml
         │
4. Stage 1: Scout agent runs → produces findings
         │
5. Stage 2: Score agent runs → evaluates findings against rubric
         │
6. Stage 3: Compile agent runs → renders report from template
         │
7. HITL check: Does this pipeline require review?
         │
    ┌────┴────┐
    │ Yes     │ No
    ▼         ▼
8a. Job → review state    8b. Job → complete
    (enters queue)              │
         │                9. Delivery (email, dashboard, webhook)
    Human approves
         │
9. Delivery
```

---

## Plugin System

Domains integrate with KAZI OS through the plugin loader. At startup, the platform:

1. Scans the `domains/` directory for subdirectories containing `manifest.yaml`
2. Validates each manifest against the expected schema
3. Registers the domain's agents with the orchestrator
4. Mounts the domain's FastAPI routes at `/api/{domain_name}/`
5. Loads the domain's scoring configuration
6. Registers the domain's triggers with the scheduler

The plugin interface is intentionally minimal — a domain needs only a `manifest.yaml` and a `routes.py` to be loadable. Everything else (agents, scoring, templates, dashboard) is optional and progressive.

See [Plugins](./plugins.md) for the full specification.

---

## Database Schema

KAZI OS uses a schema-per-domain approach in PostgreSQL (via Supabase):

```
platform.*              ← Shared tables (users, orgs, jobs, agent registry)
{domain_name}.*         ← Domain-specific tables (engagements, reports, etc.)
```

### Platform Schema

| Table | Purpose |
|-------|---------|
| `platform.users` | User accounts (linked to Supabase Auth) |
| `platform.organizations` | Multi-tenant org structure |
| `platform.agent_jobs` | Job execution log (status, timing, input/output refs) |
| `platform.agent_registry` | Registered agents across all domains |
| `platform.subscriptions` | Billing/plan tracking |

### Domain Schemas

Each domain defines its own tables. For example, a competitive intelligence domain might have:

| Table | Purpose |
|-------|--------|
| `market_intel.projects` | Client projects and focus areas |
| `market_intel.signals` | Discovered market signals |
| `market_intel.briefs` | Generated intelligence briefs |
| `market_intel.scores` | Historical relevance scores |

Row-Level Security (RLS) policies ensure data isolation between organizations.

---

## API Layer

The API server is built on FastAPI and exposes:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Platform health check |
| `GET /api/domains` | List registered domains |
| `POST /api/jobs` | Create a new job (triggers pipeline) |
| `GET /api/jobs/{id}` | Get job status and output |
| `GET /api/review` | List items in review queue |
| `POST /api/review/{id}/approve` | Approve a review item |
| `POST /api/review/{id}/reject` | Reject a review item |
| `/api/{domain_name}/*` | Domain-specific routes (auto-mounted from plugin) |

All routes require authentication via Supabase Auth (JWT bearer token). Domain routes inherit the platform's auth middleware automatically.

---

## Deployment Topology

### Development (local)

```
┌─────────────────────────────┐
│  kazi serve (single process) │
│  ├── FastAPI server          │
│  ├── Plugin loader           │
│  └── Scheduler               │
├─────────────────────────────┤
│  Supabase (Docker)           │
│  ├── PostgreSQL              │
│  ├── Auth                    │
│  └── Storage                 │
└─────────────────────────────┘
```

### Production (hosted)

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  KAZI API    │    │  Dashboard   │    │  Supabase    │
│  (FastAPI)   │◄──►│  (React)     │    │  (hosted)    │
│  + Scheduler │    │              │    │              │
└──────┬───────┘    └──────────────┘    └──────┬───────┘
       │                                        │
       └────────────────────────────────────────┘
```

---

## Design Principles

The architecture is guided by these principles:

1. **Agents are stateless.** All state lives in the job context and database. Agents can be replaced, retried, or parallelized without side effects.

2. **Domains are isolated.** A domain cannot access another domain's data or agents. The platform mediates all cross-domain interaction.

3. **The platform is domain-agnostic.** KAZI OS knows nothing about your specific domain. It knows about pipelines, scores, templates, and delivery.

4. **Progressive complexity.** A domain can start with one agent and no scoring. It can add scoring, templates, HITL, and monitoring incrementally.

5. **Harness over autonomy.** Agents operate within defined guardrails (scoring rubrics, structured output schemas, human review gates). The platform constrains, not just enables.

---

## References

[1]: https://martinfowler.com/articles/engineering-practices-llm.html "Engineering Practices for LLM Application Development — Martin Fowler"
