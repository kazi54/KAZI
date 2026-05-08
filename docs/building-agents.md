# Building Agents

This guide covers everything you need to know to build production-quality agents for KAZI OS — from the simplest single-purpose agent to complex multi-step reasoning agents with tool access and retry logic.

---

## Agent Fundamentals

An agent in KAZI OS is a **unit of work** that answers one question and produces structured output. Agents are:

- **Stateless** — no data persists between invocations
- **Async** — all agents use `async/await` for non-blocking execution
- **Typed** — inputs and outputs conform to declared schemas
- **Composable** — agents chain into pipelines via the orchestrator

Every agent extends `BaseAgent` and implements a single method: `run()`.

```python
from kazi.agents import BaseAgent

class MyAgent(BaseAgent):
    name = "my_agent"
    description = "What this agent does in one sentence"

    async def run(self, input_data: dict) -> dict:
        # Your logic here
        return {"result": "value"}
```

---

## The BaseAgent API

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `str` | Yes | Unique identifier within the domain |
| `description` | `str` | Yes | Human-readable purpose statement |
| `version` | `str` | No | Semantic version (default: "0.1.0") |
| `max_retries` | `int` | No | Retry count on failure (default: 3) |
| `backoff_base` | `float` | No | Exponential backoff base in seconds (default: 2.0) |
| `timeout` | `float` | No | Max execution time in seconds (default: 300) |
| `output_schema` | `dict` | No | JSON Schema for output validation |
| `tools` | `list[str]` | No | External tools this agent requires |

| Method | Signature | Description |
|--------|-----------|-------------|
| `run` | `async run(self, input_data: dict) -> dict` | Core logic — must be implemented |
| `validate_input` | `validate_input(self, input_data: dict) -> bool` | Optional input validation |
| `on_error` | `async on_error(self, error: Exception, input_data: dict) -> dict` | Error handler (default: re-raise) |
| `on_retry` | `async on_retry(self, attempt: int, error: Exception) -> None` | Called before each retry |

---

## Specialized Agent Types

KAZI OS provides specialized base classes for common agent roles. These add domain-specific conventions and helper methods.

### BaseScoutAgent

Agents that discover, research, or fetch information from external sources.

```python
from kazi.agents import BaseScoutAgent

class PatentScout(BaseScoutAgent):
    name = "patent_scout"
    description = "Fetches patent data from USPTO and builds a patent profile"
    tools = ["uspto_api", "google_patents"]

    async def run(self, input_data: dict) -> dict:
        patent_number = input_data["patent_number"]
        
        # Fetch primary patent
        patent = await self.tools.uspto_api.fetch(patent_number)
        
        # Fetch citations
        citations = await self.tools.google_patents.citations(patent_number)
        
        return {
            "patent": patent,
            "citations": citations,
            "citation_count": len(citations),
            "family_size": patent.get("family_size", 1),
        }
```

**Conventions for scout agents:**
- Return raw data, not interpretations
- Include metadata (counts, timestamps, source identifiers)
- Handle missing data gracefully (return `None` fields, not errors)

### BaseScoreAgent

Agents that evaluate items against a scoring rubric.

```python
from kazi.agents import BaseScoreAgent

class CommercialScoreAgent(BaseScoreAgent):
    name = "commercial_scorer"
    description = "Scores patent commercial potential across 5 dimensions"

    async def run(self, input_data: dict) -> dict:
        patent_data = input_data["_context"]["patent_scout"]
        
        scores = {
            "market_size": self.score_market(patent_data),
            "competitive_advantage": self.score_competition(patent_data),
            "implementation_readiness": self.score_readiness(patent_data),
            "licensing_potential": self.score_licensing(patent_data),
            "strategic_alignment": self.score_alignment(patent_data),
        }
        
        # Use the scoring system from scoring.yaml
        overall = self.scoring_system.compute(scores)
        tier = self.scoring_system.legend.classify(overall)
        
        return {
            "dimensions": scores,
            "overall_score": overall,
            "tier": tier.name,
            "recommendation": tier.action,
        }
    
    def score_market(self, data: dict) -> float:
        # Domain-specific scoring logic
        ...
```

**Conventions for score agents:**
- Always return `overall_score` (0-100), `dimensions` (dict), and `tier` (string)
- Use the domain's `scoring.yaml` configuration via `self.scoring_system`
- Document the reasoning behind each dimension score

### BaseProfileAgent

Agents that build structured profiles of entities (people, companies, technologies).

```python
from kazi.agents import BaseProfileAgent

class InventorProfileAgent(BaseProfileAgent):
    name = "inventor_profiler"
    description = "Builds a structured profile of the patent inventor"

    async def run(self, input_data: dict) -> dict:
        inventor_name = input_data["inventor_name"]
        
        return {
            "name": inventor_name,
            "affiliation": await self.lookup_affiliation(inventor_name),
            "patent_count": await self.count_patents(inventor_name),
            "h_index": await self.lookup_h_index(inventor_name),
            "domains": await self.classify_domains(inventor_name),
            "collaboration_network": await self.find_collaborators(inventor_name),
        }
```

### BaseCompileAgent

Agents that assemble final deliverables from accumulated pipeline data.

```python
from kazi.agents import BaseCompileAgent

class ReportCompiler(BaseCompileAgent):
    name = "report_compiler"
    description = "Renders the final audit report from scored data"
    template = "templates/audit_report_v2.html"

    async def run(self, input_data: dict) -> dict:
        context = input_data["_context"]
        
        # Gather all data from previous stages
        report_data = {
            "patent": context["patent_scout"]["patent"],
            "scores": context["commercial_scorer"],
            "inventor": context["inventor_profiler"],
            "licensees": context["licensee_finder"]["candidates"],
        }
        
        # Render template
        html = self.render_template(self.template, report_data)
        
        return {
            "report_html": html,
            "report_title": f"CARTA Audit — {report_data['patent']['title']}",
            "delivery_format": "html",
        }
```

---

## Accessing Pipeline Context

When agents run inside a pipeline, they receive the accumulated outputs of all previous stages via `input_data["_context"]`. The context is keyed by agent name.

```python
# If the pipeline is: scout → score → compile
# Then the compile agent sees:
input_data["_context"] = {
    "scout": { ... scout's output ... },
    "score": { ... score's output ... },
}
```

The agent's own output is **not** in `_context` — it becomes part of the context for subsequent stages only after the current agent completes.

---

## Tool Access

Agents declare tools they need via the `tools` attribute. The orchestrator injects tool instances at runtime.

```python
class MyAgent(BaseAgent):
    tools = ["web_search", "llm"]

    async def run(self, input_data: dict) -> dict:
        # Tools are available as self.tools.<tool_name>
        search_results = await self.tools.web_search("quantum computing patents 2024")
        
        # LLM tool for generation/analysis
        analysis = await self.tools.llm.complete(
            prompt=f"Analyze these results: {search_results}",
            model="gpt-4o",
            temperature=0.2,
        )
        
        return {"analysis": analysis}
```

**Available built-in tools:**

| Tool | Purpose |
|------|---------|
| `llm` | Language model access (OpenAI, Anthropic, etc.) |
| `web_search` | Web search via configured provider |
| `http` | Generic HTTP client for API calls |
| `storage` | File storage (Supabase Storage) |
| `db` | Database access (Supabase client) |

Domains can register custom tools in their `manifest.yaml`.

---

## Error Handling

### Automatic Retry

By default, agents retry up to 3 times with exponential backoff when `run()` raises an exception. Configure this per-agent:

```python
class FragileAgent(BaseAgent):
    max_retries = 5
    backoff_base = 1.0      # Start at 1 second
    backoff_max = 60.0      # Cap at 60 seconds
    timeout = 120.0         # Kill after 2 minutes
```

### Custom Error Handling

Override `on_error` for domain-specific error recovery:

```python
class ResilientAgent(BaseAgent):
    async def on_error(self, error: Exception, input_data: dict) -> dict:
        if isinstance(error, RateLimitError):
            # Return partial results instead of failing
            return {"partial": True, "data": input_data.get("_last_good_result")}
        raise error  # Re-raise for retry
```

### Validation-Repair Loop

If you define `output_schema`, the pipeline executor validates output and re-invokes the agent with error feedback:

```python
class StrictAgent(BaseAgent):
    output_schema = {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "tier": {"type": "string", "enum": ["abandon", "evaluate", "pursue", "fast_track"]},
    }

    async def run(self, input_data: dict) -> dict:
        # If previous attempt failed validation, errors are in:
        if "_validation_errors" in input_data:
            # Adjust approach based on what went wrong
            errors = input_data["_validation_errors"]
            ...
        
        return {"score": 75, "tier": "pursue"}
```

---

## Testing Agents

### Unit Testing

Test agents in isolation by calling `run()` directly:

```python
import pytest
from my_domain.agents.scout import PatentScout

@pytest.mark.asyncio
async def test_patent_scout():
    agent = PatentScout()
    result = await agent.run({"patent_number": "US11234891"})
    
    assert "patent" in result
    assert result["patent"]["number"] == "US11234891"
    assert "citations" in result
```

### Integration Testing

Test agents within a pipeline:

```python
from kazi.orchestrator import Pipeline
from my_domain.agents import ScoutAgent, ScoreAgent

@pytest.mark.asyncio
async def test_scout_score_pipeline():
    pipeline = Pipeline(stages=[ScoutAgent(), ScoreAgent()])
    result = await pipeline.execute({"patent_number": "US11234891"})
    
    assert "overall_score" in result
    assert 0 <= result["overall_score"] <= 100
```

### Mocking Tools

Use dependency injection to mock external tools in tests:

```python
@pytest.mark.asyncio
async def test_with_mock_tools():
    agent = PatentScout()
    agent.tools.uspto_api = MockUSPTOAPI(fixture="sample_patent.json")
    
    result = await agent.run({"patent_number": "US11234891"})
    assert result["patent"]["title"] == "Sample Patent Title"
```

---

## Best Practices

### Do

- **Keep agents focused.** One agent, one question. If your agent does two things, split it into two agents.
- **Return structured data.** Always return dictionaries with consistent keys. Downstream agents and templates depend on predictable output shapes.
- **Handle missing data.** External APIs fail. Return `None` for missing fields rather than crashing.
- **Log decisions.** When an agent makes a judgment call (e.g., choosing between two data sources), log the reasoning.
- **Version your agents.** Bump the version when output schema changes. This helps with debugging and rollback.

### Do Not

- **Do not store state between calls.** Agents are stateless. Use the job context for inter-agent communication.
- **Do not call other agents directly.** Let the pipeline/orchestrator handle coordination. If you need another agent's output, it should be a prior stage in the pipeline.
- **Do not hardcode API keys.** Use environment variables or the platform's secret management.
- **Do not generate fake data.** If an external source is unavailable, return an error or partial result — never fabricate.
- **Do not ignore timeouts.** Set appropriate timeouts for external calls. A hung agent blocks the entire pipeline.

---

## Agent Checklist

Before deploying an agent to production, verify:

| Check | Status |
|-------|--------|
| `name` and `description` are set | |
| `output_schema` is defined | |
| Unit tests pass | |
| Error handling covers expected failure modes | |
| Timeout is appropriate for the workload | |
| No hardcoded secrets | |
| Logging captures key decisions | |
| Output is deterministic given the same input (or documented as non-deterministic) | |
