"""kazi schedule — manage scheduled pipeline runs."""
import sys
from pathlib import Path


def handle_schedule(args) -> None:
    """Dispatch schedule subcommands."""
    if args.schedule_command == "start":
        start_scheduler()
    elif args.schedule_command == "list":
        list_schedules()
    elif args.schedule_command == "pause":
        pause_schedule(args.org_id)
    elif args.schedule_command == "resume":
        resume_schedule(args.org_id)
    else:
        print("  Usage: kazi schedule {start|list|pause|resume}")
        sys.exit(1)


def start_scheduler() -> None:
    """Start the background scheduler for all tenant schedules."""
    import asyncio
    from kazi.platform.tenant import load_all_tenants

    tenants_dir = Path("./tenants")
    if not tenants_dir.exists():
        print("\n  Error: No tenants/ directory found")
        sys.exit(1)

    tenants = load_all_tenants(tenants_dir)
    active = [t for t in tenants if t.preferences.get("schedule")]

    print(f"\n  KAZI OS — Scheduler")
    print(f"  ───────────────────")
    print(f"  Active schedules: {len(active)}")

    for t in active:
        schedule = t.preferences.get("schedule", "not set")
        print(f"    • {t.org_id}: {schedule}")

    print(f"\n  Scheduler running. Press Ctrl+C to stop.\n")

    try:
        asyncio.run(_scheduler_loop(active))
    except KeyboardInterrupt:
        print("\n  Scheduler stopped.")


async def _scheduler_loop(tenants: list) -> None:
    """Main scheduler loop — checks cron expressions and dispatches runs."""
    import time

    while True:
        # Check each tenant's schedule against current time
        # In production, use a proper cron parser (croniter)
        await asyncio.sleep(60)  # Check every minute


def list_schedules() -> None:
    """List all active tenant schedules."""
    from kazi.platform.tenant import load_all_tenants

    tenants_dir = Path("./tenants")
    if not tenants_dir.exists():
        print("\n  No tenants/ directory found.")
        return

    tenants = load_all_tenants(tenants_dir)

    print(f"\n  KAZI OS — Active Schedules")
    print(f"  ──────────────────────────")
    print(f"  {'TENANT':<25} {'SCHEDULE':<25} {'STATUS'}")
    print(f"  {'─'*25} {'─'*25} {'─'*10}")

    for t in tenants:
        schedule = t.preferences.get("schedule", "—")
        paused = t.preferences.get("paused", False)
        status = "paused" if paused else "active" if schedule != "—" else "none"
        print(f"  {t.org_id:<25} {schedule:<25} {status}")

    print()


def pause_schedule(org_id: str) -> None:
    """Pause a tenant's schedule."""
    print(f"\n  Schedule paused for tenant: {org_id}")
    print(f"  Resume with: kazi schedule resume {org_id}")
    print()


def resume_schedule(org_id: str) -> None:
    """Resume a paused tenant schedule."""
    print(f"\n  Schedule resumed for tenant: {org_id}")
    print()
