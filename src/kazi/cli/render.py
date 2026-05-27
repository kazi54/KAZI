"""kazi render — render reports from pipeline run data."""
import json
import sys
from pathlib import Path
from typing import Optional


def render_report(
    run_id: str,
    template: str,
    output_format: str = "html",
    output_path: Optional[str] = None,
) -> None:
    """Render a report from a completed pipeline run."""
    from kazi.state.store import create_state_store
    from kazi.delivery.renderer import TemplateRenderer

    print(f"\n  KAZI OS — Report Renderer")
    print(f"  ─────────────────────────")
    print(f"  Run ID:      {run_id}")
    print(f"  Template:    {template}")
    print(f"  Format:      {output_format}")

    # Load run data
    state_store = create_state_store(Path(".kazi/state"))
    run = state_store.get_run(run_id)

    if not run:
        print(f"\n  Error: Run '{run_id}' not found")
        sys.exit(1)

    # Load template
    template_path = Path(template)
    if not template_path.exists():
        print(f"\n  Error: Template not found: {template}")
        sys.exit(1)

    # Build render context from run data
    context = {
        "run_id": run_id,
        "pipeline": run.get("pipeline_name", "unknown"),
        "tenant_id": run.get("tenant_id", "default"),
        "timestamp": run.get("completed_at", ""),
        "stages": run.get("stage_results", []),
        "output": run.get("result", {}),
        **run.get("context", {}),
    }

    # Render
    renderer = TemplateRenderer(search_paths=[template_path.parent])
    rendered = renderer.render(template_path.name, context)

    # Determine output path
    if output_path:
        out = Path(output_path)
    else:
        out = Path(f".kazi/output/{run_id}.{output_format}")
        out.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    if output_format == "json":
        out.write_text(json.dumps(context, indent=2, default=str))
    elif output_format == "md":
        out.write_text(rendered)
    elif output_format == "pdf":
        # Render HTML first, then convert
        html_content = rendered
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(str(out))
        except ImportError:
            print("\n  Warning: weasyprint not installed. Saving as HTML instead.")
            out = out.with_suffix(".html")
            out.write_text(html_content)
    else:
        out.write_text(rendered)

    print(f"  Output:      {out}")
    print(f"\n  Report rendered successfully.")
    print()
