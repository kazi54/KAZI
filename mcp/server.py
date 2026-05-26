"""
KAZI OS — MCP Server

Exposes the KAZI OS platform over the Model Context Protocol.
Any AI model (Claude, GPT, local models) can connect and operate
pipelines, manage tenants, render reports, and query state.

Usage:
    $ kazi mcp start
    $ python -m kazi.mcp.server

Or add to Claude Desktop config:
    {
        "mcpServers": {
            "kazi-os": {
                "command": "python",
                "args": ["-m", "kazi.mcp.server"],
                "env": {
                    "KAZI_PROJECT_DIR": "/path/to/your/project"
                }
            }
        }
    }
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import (
    Tool,
    TextContent,
    Resource,
    ResourceTemplate,
    Prompt,
    PromptMessage,
    PromptArgument,
    GetPromptResult,
)

# ─── Configuration ────────────────────────────────────────────────────────────

PROJECT_DIR = Path(os.environ.get("KAZI_PROJECT_DIR", "."))
DOMAINS_DIR = PROJECT_DIR / "domains"
TENANTS_DIR = PROJECT_DIR / "tenants"
STATE_DIR = PROJECT_DIR / ".kazi" / "state"

# ─── Server Instance ──────────────────────────────────────────────────────────

server = Server("kazi-os")


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS — Functions the AI can call
# ═══════════════════════════════════════════════════════════════════════════════


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Register all KAZI OS tools."""
    return [
        Tool(
            name="kazi_run_pipeline",
            description=(
                "Execute a pipeline by name. Optionally scope to a specific tenant. "
                "Returns the run ID and execution result."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "pipeline_name": {
                        "type": "string",
                        "description": "Name of the pipeline to run (as defined in manifest.yaml)",
                    },
                    "tenant": {
                        "type": "string",
                        "description": "Tenant org_id to scope the run to. Optional.",
                    },
                    "input": {
                        "type": "object",
                        "description": "Input data to pass to the pipeline. Optional.",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, validate the pipeline without executing. Default false.",
                    },
                },
                "required": ["pipeline_name"],
            },
        ),
        Tool(
            name="kazi_resume_checkpoint",
            description=(
                "Resume a paused pipeline by resolving a human-in-the-loop checkpoint. "
                "Provide the run ID and whether to approve or reject."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The run ID of the paused pipeline",
                    },
                    "resolution": {
                        "type": "string",
                        "enum": ["approved", "rejected", "revision_requested"],
                        "description": "How to resolve the checkpoint",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the resolution. Optional.",
                    },
                },
                "required": ["run_id", "resolution"],
            },
        ),
        Tool(
            name="kazi_retry_run",
            description="Retry a failed pipeline run from the beginning or a specific stage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The run ID to retry",
                    },
                    "from_stage": {
                        "type": "integer",
                        "description": "Stage index to retry from (0-based). Omit to retry from beginning.",
                    },
                },
                "required": ["run_id"],
            },
        ),
        Tool(
            name="kazi_score",
            description=(
                "Score an item using a domain's scoring system. "
                "Returns dimensional scores, weighted total, and tier classification."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain name (must have a scoring.yaml)",
                    },
                    "item": {
                        "type": "object",
                        "description": "The item to score (structure depends on domain scoring dimensions)",
                    },
                },
                "required": ["domain", "item"],
            },
        ),
        Tool(
            name="kazi_validate_config",
            description=(
                "Validate a KAZI config file (manifest, scoring, or tenant). "
                "Returns validation result with errors and warnings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the config file to validate (relative to project dir)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="kazi_add_tenant",
            description="Create a new tenant configuration from template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_id": {
                        "type": "string",
                        "description": "Unique identifier for the tenant (lowercase, hyphens allowed)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable name of the tenant/organization",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Which domain this tenant operates in",
                    },
                },
                "required": ["org_id", "name", "domain"],
            },
        ),
        Tool(
            name="kazi_list_tenants",
            description="List all configured tenants with their domains and destination counts.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="kazi_render_report",
            description=(
                "Render a report from a completed pipeline run using a Jinja2 template. "
                "Returns the rendered content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The run ID to render a report for",
                    },
                    "template": {
                        "type": "string",
                        "description": "Path to the Jinja2 template file (relative to project dir)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["html", "md", "json"],
                        "description": "Output format. Default: html",
                    },
                },
                "required": ["run_id", "template"],
            },
        ),
        Tool(
            name="kazi_emit_event",
            description=(
                "Emit an event that can trigger event-driven pipelines. "
                "Returns which pipelines were triggered."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_name": {
                        "type": "string",
                        "description": "Name of the event to emit",
                    },
                    "data": {
                        "type": "object",
                        "description": "Event payload data",
                    },
                },
                "required": ["event_name"],
            },
        ),
        Tool(
            name="kazi_get_run_status",
            description="Get the current status and details of a pipeline run.",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The run ID to check",
                    },
                },
                "required": ["run_id"],
            },
        ),
        Tool(
            name="kazi_list_pipelines",
            description="List all available pipelines across all loaded domains.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""

    if name == "kazi_run_pipeline":
        return await _tool_run_pipeline(arguments)
    elif name == "kazi_resume_checkpoint":
        return await _tool_resume_checkpoint(arguments)
    elif name == "kazi_retry_run":
        return await _tool_retry_run(arguments)
    elif name == "kazi_score":
        return await _tool_score(arguments)
    elif name == "kazi_validate_config":
        return await _tool_validate_config(arguments)
    elif name == "kazi_add_tenant":
        return await _tool_add_tenant(arguments)
    elif name == "kazi_list_tenants":
        return await _tool_list_tenants(arguments)
    elif name == "kazi_render_report":
        return await _tool_render_report(arguments)
    elif name == "kazi_emit_event":
        return await _tool_emit_event(arguments)
    elif name == "kazi_get_run_status":
        return await _tool_get_run_status(arguments)
    elif name == "kazi_list_pipelines":
        return await _tool_list_pipelines(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ─── Tool Implementations ────────────────────────────────────────────────────


async def _tool_run_pipeline(args: dict) -> list[TextContent]:
    """Execute a pipeline."""
    import yaml
    from kazi.orchestrator.builder import PipelineBuilder
    from kazi.agents.registry import AgentRegistry
    from kazi.state.store import create_state_store

    pipeline_name = args["pipeline_name"]
    tenant_id = args.get("tenant")
    input_data = args.get("input", {})
    dry_run = args.get("dry_run", False)

    # Find manifest containing this pipeline
    manifest_path = _find_manifest(pipeline_name)
    if not manifest_path:
        return [TextContent(type="text", text=f"Error: No manifest found containing pipeline '{pipeline_name}'")]

    # Build pipeline
    registry = AgentRegistry()
    registry.discover(manifest_path.parent / "agents")

    builder = PipelineBuilder(registry)
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    pipelines = builder.build_all(manifest)
    if pipeline_name not in pipelines:
        available = ", ".join(pipelines.keys())
        return [TextContent(type="text", text=f"Error: Pipeline '{pipeline_name}' not found. Available: {available}")]

    pipeline = pipelines[pipeline_name]

    if dry_run:
        stages = [s.name for s in pipeline.stages]
        return [TextContent(type="text", text=json.dumps({
            "status": "valid",
            "pipeline": pipeline_name,
            "stages": stages,
            "stage_count": len(stages),
        }, indent=2))]

    # Execute
    context = {"org_id": tenant_id} if tenant_id else {}
    context.update(input_data)

    result = await pipeline.run(context)

    # Persist state
    state_store = create_state_store(STATE_DIR)
    run_id = state_store.create_run(pipeline_name, tenant_id or "default", context)
    state_store.complete_run(run_id, result)

    return [TextContent(type="text", text=json.dumps({
        "run_id": run_id,
        "pipeline": pipeline_name,
        "tenant": tenant_id or "default",
        "status": "completed" if result.get("status") != "error" else "failed",
        "result": result,
    }, indent=2, default=str))]


async def _tool_resume_checkpoint(args: dict) -> list[TextContent]:
    """Resume a paused pipeline."""
    from kazi.hitl.processor import HITLProcessor, Resolution

    processor = HITLProcessor(state_dir=STATE_DIR)
    res = Resolution(
        status=args["resolution"],
        reason=args.get("reason"),
        resolved_by="mcp",
    )

    result = await processor.resolve(args["run_id"], res)
    return [TextContent(type="text", text=json.dumps({
        "run_id": args["run_id"],
        "resolution": args["resolution"],
        "result": str(result),
    }, indent=2))]


async def _tool_retry_run(args: dict) -> list[TextContent]:
    """Retry a failed run."""
    from kazi.state.store import create_state_store

    state_store = create_state_store(STATE_DIR)
    run = state_store.get_run(args["run_id"])

    if not run:
        return [TextContent(type="text", text=f"Error: Run '{args['run_id']}' not found")]

    # Re-execute the pipeline with original context
    new_args = {
        "pipeline_name": run.get("pipeline_name", "unknown"),
        "tenant": run.get("tenant_id"),
        "input": run.get("context", {}),
    }
    return await _tool_run_pipeline(new_args)


async def _tool_score(args: dict) -> list[TextContent]:
    """Score an item using a domain's scoring system."""
    import yaml
    from kazi.scoring.dimensions import ScoringDimension

    domain = args["domain"]
    item = args["item"]

    scoring_path = DOMAINS_DIR / domain / "scoring.yaml"
    if not scoring_path.exists():
        return [TextContent(type="text", text=f"Error: No scoring.yaml found for domain '{domain}'")]

    with open(scoring_path) as f:
        scoring_config = yaml.safe_load(f)

    # Calculate scores
    dimensions = scoring_config.get("dimensions", [])
    results = []
    total_weight = 0
    weighted_sum = 0

    for dim in dimensions:
        dim_name = dim["name"]
        weight = dim.get("weight", 1.0)
        score = item.get(dim_name, 0)

        results.append({
            "dimension": dim_name,
            "score": score,
            "weight": weight,
            "weighted": score * weight,
        })
        weighted_sum += score * weight
        total_weight += weight

    final_score = weighted_sum / total_weight if total_weight > 0 else 0

    # Determine tier
    tiers = scoring_config.get("tiers", [])
    tier = "unclassified"
    for t in tiers:
        if final_score >= t.get("min", 0):
            tier = t.get("name", "unknown")
            break

    return [TextContent(type="text", text=json.dumps({
        "domain": domain,
        "final_score": round(final_score, 3),
        "tier": tier,
        "dimensions": results,
    }, indent=2))]


async def _tool_validate_config(args: dict) -> list[TextContent]:
    """Validate a config file."""
    import yaml
    from kazi.utils.validation import validate_manifest, validate_scoring_config, validate_tenant_config

    file_path = PROJECT_DIR / args["file_path"]
    if not file_path.exists():
        return [TextContent(type="text", text=f"Error: File not found: {file_path}")]

    with open(file_path) as f:
        config = yaml.safe_load(f)

    # Detect type
    filename = file_path.name.lower()
    if "manifest" in filename or "pipelines" in config:
        result = validate_manifest(config)
        file_type = "manifest"
    elif "scoring" in filename or "dimensions" in config:
        result = validate_scoring_config(config)
        file_type = "scoring"
    elif "org_id" in config:
        result = validate_tenant_config(config)
        file_type = "tenant"
    else:
        result = validate_manifest(config)
        file_type = "unknown"

    return [TextContent(type="text", text=json.dumps({
        "file": str(file_path),
        "type": file_type,
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
    }, indent=2))]


async def _tool_add_tenant(args: dict) -> list[TextContent]:
    """Create a new tenant config."""
    org_id = args["org_id"]
    name = args["name"]
    domain = args["domain"]

    TENANTS_DIR.mkdir(exist_ok=True)
    target = TENANTS_DIR / f"{org_id}.yaml"

    if target.exists():
        return [TextContent(type="text", text=f"Error: Tenant '{org_id}' already exists")]

    content = f"""# Tenant: {name}
org_id: "{org_id}"
name: "{name}"
domain: "{domain}"

destinations:
  review:
    adapter: webhook
    config:
      url: "https://example.com/webhook/review"
  publish:
    adapter: webhook
    config:
      url: "https://example.com/webhook/publish"

preferences:
  timezone: "UTC"
  schedule: "0 9 * * 1-5"
  auto_approve: false
"""
    target.write_text(content)

    return [TextContent(type="text", text=json.dumps({
        "status": "created",
        "org_id": org_id,
        "name": name,
        "domain": domain,
        "file": str(target),
        "next_step": "Edit the tenant file to configure real destinations and secrets",
    }, indent=2))]


async def _tool_list_tenants(args: dict) -> list[TextContent]:
    """List all tenants."""
    import yaml

    if not TENANTS_DIR.exists():
        return [TextContent(type="text", text="No tenants/ directory found")]

    tenants = []
    for f in sorted(TENANTS_DIR.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                config = yaml.safe_load(fh)
            tenants.append({
                "org_id": config.get("org_id", f.stem),
                "name": config.get("name", ""),
                "domain": config.get("domain", ""),
                "destinations": len(config.get("destinations", {})),
            })
        except Exception:
            continue

    return [TextContent(type="text", text=json.dumps({
        "count": len(tenants),
        "tenants": tenants,
    }, indent=2))]


async def _tool_render_report(args: dict) -> list[TextContent]:
    """Render a report from run data."""
    from kazi.state.store import create_state_store
    from kazi.delivery.renderer import TemplateRenderer

    state_store = create_state_store(STATE_DIR)
    run = state_store.get_run(args["run_id"])

    if not run:
        return [TextContent(type="text", text=f"Error: Run '{args['run_id']}' not found")]

    template_path = PROJECT_DIR / args["template"]
    if not template_path.exists():
        return [TextContent(type="text", text=f"Error: Template not found: {template_path}")]

    context = {
        "run_id": args["run_id"],
        "pipeline": run.get("pipeline_name", ""),
        "tenant_id": run.get("tenant_id", ""),
        "output": run.get("result", {}),
        **run.get("context", {}),
    }

    renderer = TemplateRenderer(search_paths=[template_path.parent])
    rendered = renderer.render(template_path.name, context)

    return [TextContent(type="text", text=rendered)]


async def _tool_emit_event(args: dict) -> list[TextContent]:
    """Emit an event and check for matching triggers."""
    import yaml

    event_name = args["event_name"]
    data = args.get("data", {})
    matched = []

    if DOMAINS_DIR.exists():
        for manifest_path in DOMAINS_DIR.glob("*/manifest.yaml"):
            if manifest_path.parent.name.startswith("_"):
                continue
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                for pipe_name, pipe_def in manifest.get("pipelines", {}).items():
                    trigger = pipe_def.get("trigger", {})
                    if trigger.get("type") == "event" and trigger.get("event") == event_name:
                        matched.append({
                            "domain": manifest_path.parent.name,
                            "pipeline": pipe_name,
                        })
            except Exception:
                continue

    return [TextContent(type="text", text=json.dumps({
        "event": event_name,
        "data": data,
        "triggered_pipelines": matched,
        "count": len(matched),
    }, indent=2))]


async def _tool_get_run_status(args: dict) -> list[TextContent]:
    """Get run status."""
    from kazi.state.store import create_state_store

    state_store = create_state_store(STATE_DIR)
    run = state_store.get_run(args["run_id"])

    if not run:
        return [TextContent(type="text", text=f"Error: Run '{args['run_id']}' not found")]

    return [TextContent(type="text", text=json.dumps(run, indent=2, default=str))]


async def _tool_list_pipelines(args: dict) -> list[TextContent]:
    """List all available pipelines."""
    import yaml

    pipelines = []
    if DOMAINS_DIR.exists():
        for manifest_path in DOMAINS_DIR.glob("*/manifest.yaml"):
            if manifest_path.parent.name.startswith("_"):
                continue
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                domain_name = manifest.get("name", manifest_path.parent.name)
                for pipe_name, pipe_def in manifest.get("pipelines", {}).items():
                    trigger = pipe_def.get("trigger", {})
                    pipelines.append({
                        "domain": domain_name,
                        "pipeline": pipe_name,
                        "trigger_type": trigger.get("type", "on_demand"),
                        "stages": len(pipe_def.get("stages", [])),
                    })
            except Exception:
                continue

    return [TextContent(type="text", text=json.dumps({
        "count": len(pipelines),
        "pipelines": pipelines,
    }, indent=2))]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _find_manifest(pipeline_name: str) -> Path | None:
    """Find the manifest containing a given pipeline."""
    import yaml

    if not DOMAINS_DIR.exists():
        return None

    for manifest_path in DOMAINS_DIR.glob("*/manifest.yaml"):
        if manifest_path.parent.name.startswith("_"):
            continue
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
            if pipeline_name in manifest.get("pipelines", {}):
                return manifest_path
        except Exception:
            continue

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCES — Data the AI can read
# ═══════════════════════════════════════════════════════════════════════════════


@server.list_resources()
async def list_resources() -> list[Resource]:
    """List available resources."""
    resources = []

    # Domain manifests
    if DOMAINS_DIR.exists():
        for manifest_path in DOMAINS_DIR.glob("*/manifest.yaml"):
            if manifest_path.parent.name.startswith("_"):
                continue
            domain = manifest_path.parent.name
            resources.append(Resource(
                uri=f"kazi://manifests/{domain}",
                name=f"Manifest: {domain}",
                description=f"Domain manifest for {domain}",
                mimeType="text/yaml",
            ))
            # Scoring config
            scoring_path = manifest_path.parent / "scoring.yaml"
            if scoring_path.exists():
                resources.append(Resource(
                    uri=f"kazi://scoring/{domain}",
                    name=f"Scoring: {domain}",
                    description=f"Scoring rubric for {domain}",
                    mimeType="text/yaml",
                ))

    # Tenant configs
    if TENANTS_DIR.exists():
        for tenant_path in sorted(TENANTS_DIR.glob("*.yaml")):
            if tenant_path.name.startswith("_"):
                continue
            org_id = tenant_path.stem
            resources.append(Resource(
                uri=f"kazi://tenants/{org_id}",
                name=f"Tenant: {org_id}",
                description=f"Tenant configuration for {org_id}",
                mimeType="text/yaml",
            ))

    # Run history
    if STATE_DIR.exists():
        for run_file in sorted(STATE_DIR.glob("runs/*.json"))[-20:]:
            run_id = run_file.stem
            resources.append(Resource(
                uri=f"kazi://runs/{run_id}",
                name=f"Run: {run_id}",
                description=f"Pipeline run record",
                mimeType="application/json",
            ))

    return resources


@server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """List resource URI templates."""
    return [
        ResourceTemplate(
            uriTemplate="kazi://manifests/{domain}",
            name="Domain Manifest",
            description="Get the manifest.yaml for a specific domain",
        ),
        ResourceTemplate(
            uriTemplate="kazi://scoring/{domain}",
            name="Scoring Config",
            description="Get the scoring.yaml for a specific domain",
        ),
        ResourceTemplate(
            uriTemplate="kazi://tenants/{org_id}",
            name="Tenant Config",
            description="Get the tenant configuration for a specific org",
        ),
        ResourceTemplate(
            uriTemplate="kazi://runs/{run_id}",
            name="Pipeline Run",
            description="Get the state and result of a pipeline run",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    parts = uri.replace("kazi://", "").split("/")

    if parts[0] == "manifests" and len(parts) == 2:
        domain = parts[1]
        path = DOMAINS_DIR / domain / "manifest.yaml"
        if path.exists():
            return path.read_text()
        return f"Error: Manifest not found for domain '{domain}'"

    elif parts[0] == "scoring" and len(parts) == 2:
        domain = parts[1]
        path = DOMAINS_DIR / domain / "scoring.yaml"
        if path.exists():
            return path.read_text()
        return f"Error: Scoring config not found for domain '{domain}'"

    elif parts[0] == "tenants" and len(parts) == 2:
        org_id = parts[1]
        path = TENANTS_DIR / f"{org_id}.yaml"
        if path.exists():
            return path.read_text()
        return f"Error: Tenant config not found for '{org_id}'"

    elif parts[0] == "runs" and len(parts) == 2:
        run_id = parts[1]
        path = STATE_DIR / "runs" / f"{run_id}.json"
        if path.exists():
            return path.read_text()
        return f"Error: Run '{run_id}' not found"

    return f"Error: Unknown resource URI: {uri}"


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPTS — Pre-built prompt templates
# ═══════════════════════════════════════════════════════════════════════════════


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompt templates."""
    return [
        Prompt(
            name="analyze_pipeline_run",
            description=(
                "Analyze a completed pipeline run — identify bottlenecks, "
                "scoring patterns, and recommendations for improvement."
            ),
            arguments=[
                PromptArgument(
                    name="run_id",
                    description="The run ID to analyze",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="draft_tenant_config",
            description=(
                "Generate a tenant configuration file for a new client. "
                "Asks about their CRM, channels, preferences, and schedule."
            ),
            arguments=[
                PromptArgument(
                    name="org_name",
                    description="Name of the organization to onboard",
                    required=True,
                ),
                PromptArgument(
                    name="domain",
                    description="Which domain they will use (e.g., content, ip-intelligence)",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="debug_failed_run",
            description=(
                "Diagnose why a pipeline run failed. Examines the run state, "
                "stage results, and error messages to suggest fixes."
            ),
            arguments=[
                PromptArgument(
                    name="run_id",
                    description="The failed run ID to debug",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="design_scoring_rubric",
            description=(
                "Help design a scoring rubric for a new domain. "
                "Guides through dimension selection, weight assignment, and tier definition."
            ),
            arguments=[
                PromptArgument(
                    name="domain",
                    description="The domain to design scoring for",
                    required=True,
                ),
                PromptArgument(
                    name="purpose",
                    description="What the scoring system is evaluating (e.g., content quality, patent value)",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="create_domain_manifest",
            description=(
                "Generate a complete domain manifest from a description of the business process. "
                "Produces manifest.yaml with pipelines, agents, and triggers."
            ),
            arguments=[
                PromptArgument(
                    name="description",
                    description="Description of the business process to automate",
                    required=True,
                ),
            ],
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """Return a prompt template with context."""
    arguments = arguments or {}

    if name == "analyze_pipeline_run":
        run_id = arguments.get("run_id", "unknown")
        # Load run data if available
        run_data = ""
        run_path = STATE_DIR / "runs" / f"{run_id}.json"
        if run_path.exists():
            run_data = run_path.read_text()

        return GetPromptResult(
            description=f"Analyze pipeline run {run_id}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Analyze this KAZI OS pipeline run and provide insights:\n\n"
                            f"Run ID: {run_id}\n"
                            f"Run Data:\n```json\n{run_data}\n```\n\n"
                            f"Please analyze:\n"
                            f"1. Execution time per stage — any bottlenecks?\n"
                            f"2. Scoring patterns — are scores consistent?\n"
                            f"3. Checkpoint resolutions — any delays in human review?\n"
                            f"4. Recommendations for pipeline optimization\n"
                        ),
                    ),
                ),
            ],
        )

    elif name == "draft_tenant_config":
        org_name = arguments.get("org_name", "Unknown Org")
        domain = arguments.get("domain", "content")

        return GetPromptResult(
            description=f"Draft tenant config for {org_name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Help me create a KAZI OS tenant configuration for:\n\n"
                            f"Organization: {org_name}\n"
                            f"Domain: {domain}\n\n"
                            f"I need to define:\n"
                            f"1. Destinations — where should pipeline outputs go? "
                            f"(Options: notion, salesforce, hubspot, airtable, webhook, email)\n"
                            f"2. Review workflow — how should human-in-the-loop work?\n"
                            f"3. Schedule — when should pipelines run?\n"
                            f"4. Preferences — timezone, auto-approve threshold, etc.\n\n"
                            f"Generate a complete tenant.yaml file with sensible defaults "
                            f"and comments explaining each section."
                        ),
                    ),
                ),
            ],
        )

    elif name == "debug_failed_run":
        run_id = arguments.get("run_id", "unknown")
        run_data = ""
        run_path = STATE_DIR / "runs" / f"{run_id}.json"
        if run_path.exists():
            run_data = run_path.read_text()

        return GetPromptResult(
            description=f"Debug failed run {run_id}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"A KAZI OS pipeline run failed. Help me diagnose the issue:\n\n"
                            f"Run ID: {run_id}\n"
                            f"Run Data:\n```json\n{run_data}\n```\n\n"
                            f"Please:\n"
                            f"1. Identify which stage failed and why\n"
                            f"2. Check if it's a transient error (retry-able) or structural\n"
                            f"3. Suggest specific fixes\n"
                            f"4. Recommend whether to retry from the failed stage or restart\n"
                        ),
                    ),
                ),
            ],
        )

    elif name == "design_scoring_rubric":
        domain = arguments.get("domain", "unknown")
        purpose = arguments.get("purpose", "general evaluation")

        return GetPromptResult(
            description=f"Design scoring rubric for {domain}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Help me design a KAZI OS scoring rubric:\n\n"
                            f"Domain: {domain}\n"
                            f"Purpose: {purpose}\n\n"
                            f"I need:\n"
                            f"1. 4-6 scoring dimensions with clear definitions\n"
                            f"2. Weight assignments that reflect priority\n"
                            f"3. Scoring criteria (what earns 0.0 vs 1.0 on each dimension)\n"
                            f"4. Tier definitions with thresholds and action labels\n\n"
                            f"Output a complete scoring.yaml file following KAZI OS format:\n"
                            f"- dimensions: list of {{name, weight, description, criteria}}\n"
                            f"- tiers: list of {{name, min, max, action}}\n"
                            f"- legend: mapping of score ranges to labels\n"
                        ),
                    ),
                ),
            ],
        )

    elif name == "create_domain_manifest":
        description = arguments.get("description", "")

        return GetPromptResult(
            description="Create domain manifest from business process",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Create a KAZI OS domain manifest for this business process:\n\n"
                            f"{description}\n\n"
                            f"Generate a complete manifest.yaml that includes:\n"
                            f"1. Domain metadata (name, version, description)\n"
                            f"2. Agent definitions (name, type, description, config)\n"
                            f"   - Types: research, evaluation, synthesis, delivery\n"
                            f"3. Pipeline definitions with stages and triggers\n"
                            f"4. Human-in-the-loop checkpoints where human review is needed\n"
                            f"5. Scoring dimensions if evaluation is involved\n\n"
                            f"Follow KAZI OS manifest schema v2. Each agent should have a clear "
                            f"single responsibility. Pipelines should flow logically from "
                            f"research → evaluation → synthesis → delivery."
                        ),
                    ),
                ),
            ],
        )

    return GetPromptResult(
        description="Unknown prompt",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=f"Unknown prompt: {name}"),
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    """Start the KAZI OS MCP server."""
    print("KAZI OS MCP Server v0.3.0", file=sys.stderr)
    print(f"Project dir: {PROJECT_DIR}", file=sys.stderr)
    asyncio.run(run_server(server))


if __name__ == "__main__":
    main()
