# Domain Template

This is a blank starter for building a new KAZI domain plugin.

## Getting Started

1. Copy this directory:
   ```bash
   cp -r domains/_template domains/my-domain
   ```

2. Edit `manifest.yaml` — set your domain name, description, and routes prefix

3. Define your agents in `agents/`:
   ```python
   from kazi.agents import BaseScoutAgent, AgentContext, AgentResult

   class MyScoutAgent(BaseScoutAgent):
       name = "my-scout"

       async def crawl(self, query: dict, context: AgentContext) -> list[dict]:
           # Your data source logic here
           return [{"title": "Result 1", "score": 85}]
   ```

4. Configure scoring in `scoring.yaml` — set dimensions, weights, and legend

5. Add report templates in `templates/` — Jinja2 HTML with `{{VARIABLE}}` placeholders

6. Define API routes in `routes.py` — the `router` attribute is auto-mounted

7. Restart KAZI:
   ```bash
   kazi serve
   ```

## Directory Structure

```
my-domain/
├── manifest.yaml    # Required — domain metadata + route config
├── routes.py        # Required — FastAPI router (must export `router`)
├── scoring.yaml     # Scoring dimensions + legend
├── agents/          # Domain-specific agent implementations
├── templates/       # Report HTML templates (Jinja2)
└── dashboard/       # React pages (auto-loaded into KAZI shell)
```
