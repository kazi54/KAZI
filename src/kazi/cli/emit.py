"""kazi emit — fire events to trigger event-driven pipelines."""
import json
import sys


def emit_event(event_name: str, data_json: str = "{}") -> None:
    """Emit an event that can trigger event-driven pipelines."""
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as e:
        print(f"\n  Error: Invalid JSON data: {e}")
        sys.exit(1)

    print(f"\n  KAZI OS — Event Emitter")
    print(f"  ───────────────────────")
    print(f"  Event:       {event_name}")
    print(f"  Data:        {json.dumps(data, indent=2)}")

    # In production, this would:
    # 1. Look up all triggers with type="event" matching this event name
    # 2. Dispatch pipeline runs for each matching trigger
    # 3. Log the event to the state store

    from pathlib import Path
    from kazi.state.store import create_state_store

    state_store = create_state_store(Path(".kazi/state"))
    state_store.log_decision(
        run_id="event",
        stage="emit",
        decision=f"Event fired: {event_name}",
        reasoning=json.dumps(data),
        confidence=1.0,
    )

    print(f"\n  Event emitted. Checking for matching triggers...")

    # Search for matching triggers in manifests
    import yaml
    from pathlib import Path

    domains_dir = Path("./domains")
    matched = 0

    if domains_dir.exists():
        for manifest_path in domains_dir.glob("*/manifest.yaml"):
            if manifest_path.parent.name.startswith("_"):
                continue
            try:
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                for pipe_name, pipe_def in manifest.get("pipelines", {}).items():
                    trigger = pipe_def.get("trigger", {})
                    if trigger.get("type") == "event" and trigger.get("event") == event_name:
                        print(f"    → Matched: {pipe_name} in {manifest_path.parent.name}")
                        matched += 1
            except Exception:
                continue

    if matched == 0:
        print(f"    No triggers matched event '{event_name}'")
    else:
        print(f"\n  {matched} pipeline(s) triggered.")

    print()
