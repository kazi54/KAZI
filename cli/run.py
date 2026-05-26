"""kazi run / resume / retry — pipeline execution commands."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional


def run_pipeline(
    pipeline_name: str,
    tenant: Optional[str] = None,
    all_tenants: bool = False,
    input_json: str = "{}",
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Run a pipeline with the given configuration."""
    payload = json.loads(input_json)

    print(f"\n  KAZI OS — Pipeline Runner")
    print(f"  ─────────────────────────")
    print(f"  Pipeline:    {pipeline_name}")

    if all_tenants:
        print(f"  Scope:       All tenants")
        _run_all_tenants(pipeline_name, payload, dry_run, verbose)
    elif tenant:
        print(f"  Tenant:      {tenant}")
        _run_single(pipeline_name, tenant, payload, dry_run, verbose)
    else:
        print(f"  Tenant:      (default — no tenant scoping)")
        _run_single(pipeline_name, None, payload, dry_run, verbose)


def _run_single(
    pipeline_name: str,
    tenant_id: Optional[str],
    payload: dict,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run a pipeline for a single tenant."""
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
