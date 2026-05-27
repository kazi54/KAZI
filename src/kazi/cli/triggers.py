"""kazi triggers — list active triggers across all domains."""
from pathlib import Path


def list_triggers() -> None:
    """List all triggers defined in loaded domain manifests."""
    import yaml

    domains_dir = Path("./domains")
    if not domains_dir.exists():
        print("\n  No domains/ directory found.")
        return

    print(f"\n  KAZI OS — Active Triggers")
    print(f"  ─────────────────────────")
    print(f"  {'DOMAIN':<15} {'PIPELINE':<20} {'TYPE':<12} {'CONFIG'}")
    print(f"  {'─'*15} {'─'*20} {'─'*12} {'─'*30}")

    total = 0
    for manifest_path in sorted(domains_dir.glob("*/manifest.yaml")):
        if manifest_path.parent.name.startswith("_"):
            continue

        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
        except Exception:
            continue

        domain_name = manifest.get("name", manifest_path.parent.name)

        for pipe_name, pipe_def in manifest.get("pipelines", {}).items():
            trigger = pipe_def.get("trigger", {})
            trigger_type = trigger.get("type", "on_demand")

            if trigger_type == "scheduled":
                config = trigger.get("cron", "—")
            elif trigger_type == "event":
                config = trigger.get("event", "—")
            else:
                config = "manual"

            print(f"  {domain_name:<15} {pipe_name:<20} {trigger_type:<12} {config}")
            total += 1

    if total == 0:
        print(f"  No triggers found.")

    print()
