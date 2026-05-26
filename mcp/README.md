# KAZI OS — MCP Server

Model Context Protocol interface to the KAZI OS platform. Allows any MCP-compatible AI model (Claude Desktop, GPT, local models) to operate pipelines, manage tenants, render reports, and query state.

## Quick Start

```bash
# Install dependencies
pip install kazi-os mcp

# Start the MCP server
cd /path/to/your/project
python -m mcp.server
```

## Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "kazi-os": {
      "command": "python",
      "args": ["-m", "mcp.server"],
      "cwd": "/path/to/your/kazi-project",
      "env": {
        "KAZI_PROJECT_DIR": "/path/to/your/kazi-project"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `kazi_run_pipeline` | Execute a pipeline (single tenant, all tenants, dry-run) |
| `kazi_resume_checkpoint` | Approve/reject a human-in-the-loop checkpoint |
| `kazi_retry_run` | Retry a failed pipeline run |
| `kazi_score` | Score an item using a domain's scoring system |
| `kazi_validate_config` | Validate manifest, scoring, or tenant configs |
| `kazi_add_tenant` | Create a new tenant configuration |
| `kazi_list_tenants` | List all configured tenants |
| `kazi_render_report` | Render a report from run data |
| `kazi_emit_event` | Fire an event to trigger event-driven pipelines |
| `kazi_get_run_status` | Check status of a pipeline run |
| `kazi_list_pipelines` | List all available pipelines |

## Available Resources

| URI Pattern | Description |
|-------------|-------------|
| `kazi://manifests/{domain}` | Domain manifest (YAML) |
| `kazi://scoring/{domain}` | Scoring rubric (YAML) |
| `kazi://tenants/{org_id}` | Tenant configuration (YAML) |
| `kazi://runs/{run_id}` | Pipeline run state (JSON) |

## Available Prompts

| Prompt | Description |
|--------|-------------|
| `analyze_pipeline_run` | Analyze a run for bottlenecks and patterns |
| `draft_tenant_config` | Generate a tenant config for a new client |
| `debug_failed_run` | Diagnose why a pipeline run failed |
| `design_scoring_rubric` | Design a scoring system for a new domain |
| `create_domain_manifest` | Generate a manifest from a business process description |

## Architecture

```
Claude Desktop / Any MCP Client
        │
        │ MCP Protocol (stdio)
        ▼
┌─────────────────────────┐
│   KAZI OS MCP Server    │
├─────────────────────────┤
│ Tools     → CLI actions │
│ Resources → Config/State│
│ Prompts   → Templates   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    KAZI OS Platform     │
│  (same modules as CLI)  │
├─────────────────────────┤
│ AgentRegistry           │
│ PipelineBuilder         │
│ ScoringSystem           │
│ DestinationRegistry     │
│ TenantConfig            │
│ HITLProcessor           │
│ StateStore              │
└─────────────────────────┘
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `KAZI_PROJECT_DIR` | Root directory of your KAZI project | `.` (current dir) |

## Development

```bash
# Run with debug output
KAZI_PROJECT_DIR=. python -m mcp.server 2>debug.log

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m mcp.server
```
