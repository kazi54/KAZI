"""kazi run — execute a pipeline manually."""

import asyncio
import json


def run_pipeline(pipeline_name: str, payload_json: str) -> None:
    """Run a pipeline with the given payload (for testing/debugging)."""
    payload = json.loads(payload_json)

    print(f"\n  Running pipeline: {pipeline_name}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    print()

    # TODO: Load the orchestrator, find the pipeline, execute
    # This will be wired up once the orchestrator is connected to the domain registry
    print("  ⚠ Manual pipeline execution not yet implemented.")
    print("  Use the API endpoint instead: POST /api/<domain>/run")
