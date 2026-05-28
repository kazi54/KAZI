"""KAZI CLI — command-line interface for the KAZI platform."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="kazi",
        description="KAZI OS — Domain-agnostic platform for AI-powered professional services",
    )
    parser.add_argument("--version", action="store_true", help="Show version")
    subparsers = parser.add_subparsers(dest="command")

    # ── kazi init <domain-name> ───────────────────────────────────────────
    init_parser = subparsers.add_parser("init", help="Create a new domain plugin")
    init_parser.add_argument("domain_name", help="Name of the domain to create")
    init_parser.add_argument("--with-scoring", action="store_true", help="Include scoring.yaml")
    init_parser.add_argument("--with-routes", action="store_true", help="Include routes.py")
    init_parser.add_argument("--template", default=None, help="Custom template directory")

    # ── kazi serve ────────────────────────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="Start the KAZI platform server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--reload", action="store_true", help="Auto-reload on changes")
    serve_parser.add_argument("--workers", type=int, default=1, help="Number of workers")

    # ── kazi run <pipeline> ───────────────────────────────────────────────
    run_parser = subparsers.add_parser("run", help="Run a pipeline")
    run_parser.add_argument("pipeline", help="Pipeline name to execute")
    run_parser.add_argument("--domain", default=".", help="Path to domain directory (default: current dir)")
    run_parser.add_argument("--tenant", default=None, help="Tenant org_id")
    run_parser.add_argument("--all-tenants", action="store_true", help="Run for all tenants")
    run_parser.add_argument("--input", default="{}", help="JSON input payload")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate without executing")
    run_parser.add_argument("--verbose", action="store_true", help="Show detailed output")

    # ── kazi resume <pipeline> ────────────────────────────────────────────
    resume_parser = subparsers.add_parser("resume", help="Resume a paused pipeline")
    resume_parser.add_argument("pipeline", help="Pipeline name")
    resume_parser.add_argument("--run-id", required=True, help="Run ID to resume")
    resume_parser.add_argument("--approve", action="store_true", help="Approve checkpoint")
    resume_parser.add_argument("--reject", action="store_true", help="Reject checkpoint")
    resume_parser.add_argument("--reason", default=None, help="Reason for rejection")

    # ── kazi retry <pipeline> ─────────────────────────────────────────────
    retry_parser = subparsers.add_parser("retry", help="Retry a failed pipeline")
    retry_parser.add_argument("pipeline", help="Pipeline name")
    retry_parser.add_argument("--run-id", required=True, help="Failed run ID")
    retry_parser.add_argument("--from-stage", type=int, default=None, help="Stage to restart from")

    # ── kazi tenant <subcommand> ──────────────────────────────────────────
    tenant_parser = subparsers.add_parser("tenant", help="Manage tenants")
    tenant_sub = tenant_parser.add_subparsers(dest="tenant_command")
    tenant_add = tenant_sub.add_parser("add", help="Create a new tenant config")
    tenant_add.add_argument("org_id", help="Tenant organization ID")
    tenant_add.add_argument("--domain", required=True, help="Domain name")
    tenant_sub.add_parser("list", help="List all tenants")
    tenant_validate = tenant_sub.add_parser("validate", help="Validate a tenant config")
    tenant_validate.add_argument("file", help="Path to tenant.yaml")
    tenant_remove = tenant_sub.add_parser("remove", help="Remove a tenant")
    tenant_remove.add_argument("org_id", help="Tenant to remove")

    # ── kazi validate <file> ──────────────────────────────────────────────
    validate_parser = subparsers.add_parser("validate", help="Validate config files")
    validate_parser.add_argument("file", help="Path to config file (manifest, scoring, tenant)")

    # ── kazi schedule <subcommand> ────────────────────────────────────────
    schedule_parser = subparsers.add_parser("schedule", help="Manage scheduled runs")
    schedule_sub = schedule_parser.add_subparsers(dest="schedule_command")
    schedule_sub.add_parser("start", help="Start the scheduler")
    schedule_sub.add_parser("list", help="List active schedules")
    schedule_pause = schedule_sub.add_parser("pause", help="Pause a tenant schedule")
    schedule_pause.add_argument("org_id", help="Tenant to pause")
    schedule_resume = schedule_sub.add_parser("resume", help="Resume a paused schedule")
    schedule_resume.add_argument("org_id", help="Tenant to resume")

    # ── kazi render ───────────────────────────────────────────────────────
    render_parser = subparsers.add_parser("render", help="Render a report from a run")
    render_parser.add_argument("--run-id", required=True, help="Run ID to render from")
    render_parser.add_argument("--template", required=True, help="Template file path")
    render_parser.add_argument("--format", default="html", choices=["html", "pdf", "md", "json"])
    render_parser.add_argument("--output", default=None, help="Output file path")

    # ── kazi emit <event> ─────────────────────────────────────────────────
    emit_parser = subparsers.add_parser("emit", help="Fire an event")
    emit_parser.add_argument("event", help="Event name (e.g., patent.filed)")
    emit_parser.add_argument("--data", default="{}", help="Event data as JSON")

    # ── kazi domains ──────────────────────────────────────────────────────
    subparsers.add_parser("domains", help="List loaded domain plugins")

    # ── kazi adapters ─────────────────────────────────────────────────────
    subparsers.add_parser("adapters", help="List available destination adapters")

    # ── kazi triggers ─────────────────────────────────────────────────────
    subparsers.add_parser("triggers", help="List active triggers")

    # ── Parse and dispatch ────────────────────────────────────────────────
    args = parser.parse_args()

    if args.version:
        from kazi import __version__
        print(f"KAZI OS v{__version__}")
        return

    if args.command == "init":
        from kazi.cli.init import init_domain
        init_domain(args.domain_name, with_scoring=args.with_scoring)

    elif args.command == "serve":
        from kazi.cli.serve import serve
        serve(host=args.host, port=args.port, reload=args.reload, workers=args.workers)

    elif args.command == "run":
        from kazi.cli.run import run_prompt_pipeline
        run_prompt_pipeline(
            pipeline_name=args.pipeline,
            domain_dir=args.domain,
            input_json=args.input,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    elif args.command == "resume":
        from kazi.cli.run import resume_pipeline
        resolution = "approved" if args.approve else "rejected" if args.reject else None
        if not resolution:
            print("  Error: must specify --approve or --reject")
            sys.exit(1)
        resume_pipeline(
            pipeline_name=args.pipeline,
            run_id=args.run_id,
            resolution=resolution,
            reason=args.reason,
        )

    elif args.command == "retry":
        from kazi.cli.run import retry_pipeline
        retry_pipeline(
            pipeline_name=args.pipeline,
            run_id=args.run_id,
            from_stage=args.from_stage,
        )

    elif args.command == "tenant":
        from kazi.cli.tenant import handle_tenant
        handle_tenant(args)

    elif args.command == "validate":
        from kazi.cli.validate import validate_file
        validate_file(args.file)

    elif args.command == "schedule":
        from kazi.cli.schedule import handle_schedule
        handle_schedule(args)

    elif args.command == "render":
        from kazi.cli.render import render_report
        render_report(
            run_id=args.run_id,
            template=args.template,
            output_format=args.format,
            output_path=args.output,
        )

    elif args.command == "emit":
        from kazi.cli.emit import emit_event
        emit_event(event_name=args.event, data_json=args.data)

    elif args.command == "domains":
        from kazi.cli.serve import list_domains
        list_domains()

    elif args.command == "adapters":
        from kazi.cli.adapters import list_adapters
        list_adapters()

    elif args.command == "triggers":
        from kazi.cli.triggers import list_triggers
        list_triggers()

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
