# Design Patterns

KAZI OS implements a catalog of proven design patterns for multi-agent systems. These patterns are organized into four categories: core agent patterns, coordination patterns, memory and learning patterns, and quality and control mechanisms.

Each pattern is described with its intent, when to use it, and how KAZI OS implements it.

---

## 1. Core Agent Patterns

These patterns define how individual agents reason and act.

### 1.1 ReAct (Reason + Act)

**Intent:** An agent alternates between reasoning about the current state and taking an action, iterating until the task is complete.

**When to use:** Complex tasks where the agent needs to plan, observe results, and adapt its approach.

**KAZI implementation:** Agents that extend `BaseScoutAgent` often use ReAct internally — they reason about what data to fetch, fetch it, evaluate whether they have enough, and continue or stop.

```python
class PatentScout(BaseScoutAgent):
    async def run(self, input_data: dict) -> dict:
        # Reason: What do I need?
        patent_number = input_data["patent_number"]
        
        # Act: Fetch from USPTO
        patent_data = await self.fetch_patent(patent_number)
        
        # Reason: Do I have enough? Are there related patents?
        if patent_data.get("family_members"):
            # Act: Fetch family
            family = await self.fetch_family(patent_data["family_id"])
            patent_data["family"] = family
        
        return patent_data
```

### 1.2 Tool Use

**Intent:** An agent delegates specific subtasks to external tools (APIs, databases, calculators) rather than attempting to solve everything with language generation.

**When to use:** When the task requires deterministic computation, real-time data access, or interaction with external systems.

**KAZI implementation:** Agents declare their tools as dependencies. The orchestrator injects tool access at runtime.

```python
class MarketScout(BaseScoutAgent):
    tools = ["web_search", "patent_database", "company_registry"]
    
    async def run(self, input_data: dict) -> dict:
        results = await self.tools.web_search(input_data["query"])
        return {"findings": results}
```

### 1.3 Prompt Chaining

**Intent:** Break a complex generation task into a sequence of simpler prompts, where each prompt's output feeds the next.

**When to use:** When a single prompt would be too complex or unreliable, but the subtasks are well-defined.

**KAZI implementation:** This is the `Pipeline` abstraction. Each stage is an agent with a focused prompt. The pipeline chains them automatically.

```yaml
# manifest.yaml
pipeline:
  stages:
    - agent: extract    # "Extract key claims from this patent"
    - agent: classify   # "Classify these claims by technology domain"
    - agent: score      # "Score commercial potential of each domain"
```

### 1.4 Template Method

**Intent:** Define the skeleton of an algorithm in a base class, deferring specific steps to subclasses.

**When to use:** When multiple agents share the same workflow structure but differ in domain-specific logic.

**KAZI implementation:** `BaseAgent` and its specialized subclasses (`BaseScoutAgent`, `BaseScoreAgent`, etc.) define the contract. Domain agents override `run()` with their specific logic while inheriting lifecycle management, logging, and error handling.

---

## 2. Coordination Patterns

These patterns define how multiple agents work together.

### 2.1 Orchestrator-Worker

**Intent:** A central coordinator dispatches tasks to specialized workers and aggregates their results.

**When to use:** When a job requires multiple heterogeneous agents that don't form a simple sequence.

**KAZI implementation:** The `Orchestrator` class manages job dispatch. It reads the pipeline definition from the domain manifest and routes work to the appropriate agents.

```python
# The orchestrator resolves which agents to call based on the manifest
job = await orchestrator.create_job(
    domain="carta",
    pipeline="full_audit",
    input_data={"patent_number": "US11234891"}
)
```

### 2.2 Pipeline

**Intent:** Process data through a linear sequence of stages, where each stage transforms the data and passes it forward.

**When to use:** When the workflow has a clear sequential dependency — each stage needs the output of the previous one.

**KAZI implementation:** The `Pipeline` class executes stages in order. Each stage receives the accumulated context from all previous stages.

```python
from kazi.orchestrator import Pipeline

pipeline = Pipeline(stages=[
    ScoutAgent(),
    ScoreAgent(),
    CompileAgent(),
])

result = await pipeline.execute({"patent_number": "US11234891"})
```

### 2.3 Fan-Out

**Intent:** Execute the same pipeline across multiple independent inputs in parallel, then collect all results.

**When to use:** When you need to process a batch of items identically (e.g., score 10 patents, evaluate 50 funding opportunities).

**KAZI implementation:** The `FanOut` class wraps a pipeline and distributes inputs across parallel executions.

```python
from kazi.orchestrator import FanOut, Pipeline

scoring_pipeline = Pipeline(stages=[ScoreAgent()])

fanout = FanOut(
    pipeline=scoring_pipeline,
    max_concurrency=5,
)

results = await fanout.execute([
    {"patent": "US11234891"},
    {"patent": "US10987654"},
    {"patent": "US11567890"},
])
```

### 2.4 Shared State

**Intent:** Multiple agents read from and write to a shared context object, enabling implicit coordination without direct message passing.

**When to use:** When agents need to build up a complex data structure incrementally, and later agents need access to earlier agents' outputs.

**KAZI implementation:** The job context (`job.context`) is a shared dictionary that accumulates outputs from each pipeline stage. Each agent can read any previous agent's output.

```python
class ScoreAgent(BaseScoreAgent):
    async def run(self, input_data: dict) -> dict:
        # Access scout's output from shared context
        findings = input_data["_context"]["scout"]["findings"]
        scores = self.evaluate(findings)
        return {"scores": scores}
```

### 2.5 Graceful Degradation

**Intent:** When a component fails, the system continues operating with reduced functionality rather than failing entirely.

**When to use:** When some pipeline stages are optional or have fallback strategies.

**KAZI implementation:** Pipeline stages can be marked as `optional: true` in the manifest. If an optional stage fails, the pipeline continues with a warning rather than aborting.

```yaml
pipeline:
  stages:
    - agent: scout
      required: true
    - agent: enrich
      required: false      # If enrichment fails, continue without it
    - agent: score
      required: true
```

---

## 3. Memory and Learning Patterns

These patterns define how the system retains and applies knowledge over time.

### 3.1 Ephemeral Context Isolation

**Intent:** Each job execution starts with a clean context. No state leaks between jobs.

**When to use:** Always — this is a default safety pattern. Prevents one client's data from contaminating another's results.

**KAZI implementation:** Every `Job` instance creates a fresh context dictionary. Agent instances are stateless — they receive input and return output without retaining anything between invocations.

### 3.2 Persistent Memory with Confidence Decay

**Intent:** Store historical scores and assessments, but reduce confidence in older data over time.

**When to use:** When monitoring previously scored items. A score from 6 months ago is less reliable than one from last week.

**KAZI implementation:** The `ScoreStore` records scores with timestamps. The `DriftDetector` applies a decay function when comparing historical scores to current assessments.

```python
# Confidence decays over time
confidence = base_confidence * decay_factor(days_since_scored)

# If confidence drops below threshold, trigger re-evaluation
if confidence < 0.6:
    await orchestrator.create_job(domain="carta", pipeline="re_score", ...)
```

### 3.3 Closed-Loop Learning

**Intent:** Use the outcomes of delivered work to improve future agent performance.

**When to use:** When you have feedback signals (client accepted/rejected recommendation, actual outcome vs. predicted outcome).

**KAZI implementation:** The platform tracks delivery outcomes. When a human reviewer modifies an agent's output before approval, that delta becomes a training signal. Over time, agents can be fine-tuned or their prompts adjusted based on accumulated corrections.

### 3.4 Scoped Tenancy

**Intent:** Data and execution are isolated per organization/client. One tenant cannot see or affect another's data.

**When to use:** Always in multi-tenant deployments.

**KAZI implementation:** Supabase Row-Level Security (RLS) policies enforce tenant isolation at the database level. The API layer passes the authenticated user's organization ID, and RLS ensures queries only return data belonging to that organization.

---

## 4. Quality and Control Mechanisms

These patterns ensure output quality and system reliability.

### 4.1 Structured Output

**Intent:** Force agents to produce output conforming to a defined schema, rather than free-form text.

**When to use:** Always — structured output enables downstream processing, scoring, and template rendering.

**KAZI implementation:** Agents declare their output schema. The orchestrator validates output against the schema before passing it to the next stage.

```python
class ScoreAgent(BaseScoreAgent):
    output_schema = {
        "overall_score": {"type": "number", "min": 0, "max": 100},
        "dimensions": {"type": "array"},
        "recommendation": {"type": "string", "enum": ["abandon", "evaluate", "pursue", "fast_track"]},
    }
```

### 4.2 Validation-Repair Loop

**Intent:** If an agent's output fails validation, automatically retry with feedback about what went wrong.

**When to use:** When agents occasionally produce malformed output that can be corrected with a targeted prompt.

**KAZI implementation:** The pipeline executor catches validation errors and re-invokes the agent with the error message appended to the input, up to a configurable retry limit.

```python
# Internal pipeline logic (simplified)
for attempt in range(max_retries):
    output = await agent.run(input_data)
    errors = validate(output, agent.output_schema)
    if not errors:
        break
    input_data["_validation_errors"] = errors  # Agent sees what went wrong
```

### 4.3 Retry with Backoff

**Intent:** When an external dependency fails (API timeout, rate limit), retry with increasing delays.

**When to use:** Any agent that calls external APIs (USPTO, grants.gov, web search).

**KAZI implementation:** The `BaseAgent` class provides built-in retry logic with exponential backoff. Agents inherit this without additional code.

```python
class BaseAgent:
    max_retries: int = 3
    backoff_base: float = 2.0  # seconds
    backoff_max: float = 30.0
```

### 4.4 Human-in-the-Loop (HITL)

**Intent:** Insert a human review gate at critical points in the pipeline to catch errors, add judgment, and maintain quality.

**When to use:** Before delivering high-stakes outputs (client reports, financial recommendations, published content).

**KAZI implementation:** The `ReviewQueue` holds items for human approval. Configurable policies determine when HITL is required.

```yaml
# manifest.yaml
hitl:
  policy: always          # always | threshold | sample
  threshold: 0.7          # Only require review if confidence < 0.7
  sample_rate: 0.1        # Review 10% of outputs randomly
  reviewers:
    - role: domain_expert
```

### 4.5 Observability and Evaluation

**Intent:** Instrument the system to measure agent performance, pipeline latency, and output quality over time.

**When to use:** Always in production. Essential for identifying degradation and guiding improvements.

**KAZI implementation:** Every job execution records timing, token usage, scores, and outcomes. The platform exposes metrics via the dashboard and optional webhook integrations.

| Metric | What it measures |
|--------|-----------------|
| `agent_latency_ms` | Time per agent execution |
| `pipeline_duration_ms` | Total pipeline time |
| `score_distribution` | Histogram of output scores |
| `hitl_modification_rate` | How often humans change agent output |
| `delivery_acceptance_rate` | Client satisfaction signal |

---

## Pattern Selection Guide

When designing a new domain, use this guide to select appropriate patterns:

| Scenario | Recommended Patterns |
|----------|---------------------|
| Simple sequential workflow | Pipeline + Structured Output |
| Batch processing | Fan-Out + Pipeline |
| High-stakes deliverables | Pipeline + HITL + Validation-Repair |
| Real-time data integration | Tool Use + Retry/Backoff |
| Long-running monitoring | Scheduled Trigger + Confidence Decay + Drift Detection |
| Multi-tenant SaaS | Scoped Tenancy + Ephemeral Context |
| Complex multi-step reasoning | ReAct + Prompt Chaining |

---

## References

[1]: https://martinfowler.com/articles/engineering-practices-llm.html "Engineering Practices for LLM Application Development — Martin Fowler"
[2]: https://www.anthropic.com/research/building-effective-agents "Building Effective Agents — Anthropic"
