"""kazi run / resume / retry — pipeline execution commands."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional


def run_prompt_pipeline(
    pipeline_name: str,
    domain_dir: str = ".",
    input_json: str = "{}",
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Run a prompt-driven pipeline from a domain directory.
    
    This is the primary execution path for KAZI OS. It reads the domain's
    YAML files and executes the pipeline via LLM calls. No Python required.
    """
    from kazi.orchestrator.prompt_executor import PromptExecutor

    domain_path = Path(domain_dir)
    manifest_path = domain_path / "manifest.yaml"

    if not manifest_path.exists():
        print(f"\n  Error: No manifest.yaml found in {domain_path.resolve()}")
        print(f"  Run 'kazi init <name>' to create a new domain, then cd into it.")
        sys.exit(1)

    payload = json.loads(input_json)

    print(f"\n  KAZI OS — Pipeline Runner")
    print(f"  ─────────────────────────")
    print(f"  Domain:      {domain_path.resolve().name}")
    print(f"  Pipeline:    {pipeline_name}")

    try:
        executor = PromptExecutor(domain_dir=domain_path)
    except Exception as e:
        print(f"\n  Error loading domain: {e}")
        sys.exit(1)

    # Dry run: show what would happen without executing
    if dry_run:
        info = asyncio.run(executor.dry_run(pipeline_name))
        print(f"\n  [DRY RUN] Pipeline validated successfully\n")
        print(f"  Model:       {info['constraints'].get('model', 'gpt-4o-mini')}")
        print(f"  Stages:      {len(info['stages'])}")
        print()
        for i, stage in enumerate(info["stages"], 1):
            print(f"    {i}. {stage['agent']}")
            print(f"       Role: {stage['role']}")
            print(f"       Goal: {stage['goal']}")
            if stage.get("uses"):
                print(f"       Uses: {', '.join(stage['uses'])}")
            print()
        print(f"  Domain files loaded:")
        for name, loaded in info["domain_files_loaded"].items():
            status = "✓" if loaded else "✗"
            print(f"    {status} {name}.yaml")
        print()
        return

    # Execute the pipeline
    if payload:
        print(f"  Input:       {json.dumps(payload)}")
    print(f"\n  Executing...\n")

    try:
        result = asyncio.run(executor.run(pipeline_name, payload))
    except Exception as e:
        print(f"\n  Error: {e}")
        sys.exit(1)

    # Display results
    print(f"  ─────────────────────────")
    print(f"  Status:      {result.status}")
    print(f"  Model:       {result.model}")
    print(f"  Tokens:      {result.total_tokens}")
    print(f"  Stages:      {len(result.stages)}")
    print()

    if verbose:
        print(f"  ── Stage Details ──\n")
        for i, stage in enumerate(result.stages, 1):
            print(f"  {i}. {stage.agent} ({stage.tokens_used} tokens)")
            if stage.council_feedback:
                print(f"     [Council review with {len(stage.council_feedback['evaluations'])} advisors]")
            print()

    # Output the final result
    print(f"  ══════════════════════════════════════════════════")
    print(f"  FINAL OUTPUT")
    print(f"  ══════════════════════════════════════════════════\n")
    print(result.final_output)
    print(f"\n  ══════════════════════════════════════════════════\n")

    # Save output to file
    output_dir = domain_path / "output"
    output_dir.mkdir(exist_ok=True)
    
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{pipeline_name}_{timestamp}.md"
    output_file.write_text(result.final_output)
    print(f"  Saved to: {output_file}")
    print()


def run_pipeline(
    pipeline_name: str,
    tenant: Optional[str] = None,
    all_tenants: bool = False,
    input_json: str = "{}",
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Legacy: Run a pipeline with the agent registry approach."""
    payload = json.loads(input_json)

    print(f"\n  KAZI OS — Pipeline Runner (legacy mode)")
    print(f"  ─────────────────────────")
    print(f"  Pipeline:    {pipeline_name}")

    if all_tenants:
        print(f"  Scope:       All tenants")
        _run_all_tenants(pipeline_name, payload, dry_run, verbose)
    elif tenant:
        print(f"  Tenant:      {tenant}")
        _run_single(pipeline_name, tenant, payload, dry_run, verbose)
    else:
        print(f"  Tenant:      (default)")
        _run_single(pipeline_name, None, payload, dry_run, verbose)


def _run_single(
    pipeline_name: str,
    tenant_id: Optional[str],
    payload: dict,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run a pipeline for a single tenant (legacy agent-registry mode)."""
    from kazi.orchestrator.builder import PipelineBuilder
    from kazi.agents.registry import AgentRegistry
    from kazi.state.store import create_state_store

    manifest_path = _find_manifest(pipeline_name)
    if not manifest_path:
        print(f"\n  Error: No manifest found containing pipeline '{pipeline_name}'")
        sys.exit(1)

    registry = AgentRegistry()
    domain_dir = manifest_path.parent
    registry.discover(domain_dir / "agents")

    builder = PipelineBuilder(registry)
    import yaml
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    pipelines = builder.build_all(manifest)
    if pipeline_name not in pipelines:
        print(f"\n  Error: Pipeline '{pipeline_name}' not found in manifest")
        print(f"  Available: {', '.join(pipelines.keys())}")
        sys.exit(1)

    pipeline = pipelines[pipeline_name]

    if dry_run:
        print(f"\n  [DRY RUN] Pipeline '{pipeline_name}' validated successfully")
        print(f"  Stages: {len(pipeline.stages)}")
        for i, stage in enumerate(pipeline.stages):
            print(f"    {i+1}. {stage.name}")
        return

    state_store = create_state_store(Path(".kazi/state"))
    print(f"\n  Executing...")
    print()

    context = {"org_id": tenant_id} if tenant_id else {}
    context.update(payload)

    result = asyncio.run(pipeline.run(context))

    run_id = state_store.create_run(pipeline_name, tenant_id or "default", context)
    state_store.complete_run(run_id, result)

    print(f"\n  Run ID:      {run_id}")
    print(f"  Status:      {'completed' if result.get('status') != 'error' else 'failed'}")

    if verbose and result:
        print(f"\n  Output:")
        print(f"  {json.dumps(result, indent=2, default=str)}")

    print()


def _run_all_tenants(
    pipeline_name: str,
    payload: dict,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run a pipeline for all configured tenants."""
    from kazi.platform.tenant import load_all_tenants

    tenants_dir = Path("./tenants")
    if not tenants_dir.exists():
        print(f"\n  Error: No tenants/ directory found")
        sys.exit(1)

    tenants = load_all_tenants(tenants_dir)
    if not tenants:
        print(f"\n  Error: No tenant configs found in {tenants_dir}")
        sys.exit(1)

    print(f"\n  Found {len(tenants)} tenant(s)")
    print()

    for tenant in tenants:
        print(f"  ── {tenant.name} ({tenant.org_id}) ──")
        _run_single(pipeline_name, tenant.org_id, payload, dry_run, verbose)


def resume_pipeline(
    pipeline_name: str,
    run_id: str,
    resolution: str,
    reason: Optional[str] = None,
) -> None:
    """Resume a paused pipeline from a HITL checkpoint."""
    from kazi.hitl.processor import HITLProcessor, Resolution

    print(f"\n  KAZI OS — Resume Pipeline")
    print(f"  ─────────────────────────")
    print(f"  Pipeline:    {pipeline_name}")
    print(f"  Run ID:      {run_id}")
    print(f"  Resolution:  {resolution}")
    if reason:
        print(f"  Reason:      {reason}")

    processor = HITLProcessor(state_dir=Path(".kazi/state"))
    res = Resolution(status=resolution, reason=reason, resolved_by="cli")

    result = asyncio.run(processor.resolve(run_id, res))
    print(f"\n  Result:      {result}")
    print()


def retry_pipeline(
    pipeline_name: str,
    run_id: str,
    from_stage: Optional[int] = None,
) -> None:
    """Retry a failed pipeline run."""
    from kazi.state.store import create_state_store

    print(f"\n  KAZI OS — Retry Pipeline")
    print(f"  ─────────────────────────")
    print(f"  Pipeline:    {pipeline_name}")
    print(f"  Run ID:      {run_id}")
    if from_stage is not None:
        print(f"  From stage:  {from_stage}")

    state_store = create_state_store(Path(".kazi/state"))
    run = state_store.get_run(run_id)

    if not run:
        print(f"\n  Error: Run '{run_id}' not found")
        sys.exit(1)

    print(f"\n  Retrying from {'stage ' + str(from_stage) if from_stage else 'beginning'}...")
    _run_single(pipeline_name, run.get("tenant_id"), run.get("context", {}), False, True)


def _find_manifest(pipeline_name: str) -> Optional[Path]:
    """Search domains/ for a manifest containing the given pipeline."""
    import yaml

    domains_dir = Path("./domains")
    if not domains_dir.exists():
        return None

    for manifest_path in domains_dir.glob("*/manifest.yaml"):
        if manifest_path.parent.name.startswith("_"):
            continue
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
            pipelines = manifest.get("pipelines", {})
            if pipeline_name in pipelines:
                return manifest_path
        except Exception:
            continue

    return None
