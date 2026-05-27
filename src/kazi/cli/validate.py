"""kazi validate — validate config files (manifest, scoring, tenant)."""
import sys
from pathlib import Path


def validate_file(file_path: str) -> None:
    """Validate a KAZI config file and report errors."""
    import yaml
    from kazi.utils.validation import (
        validate_manifest,
        validate_scoring_config,
        validate_tenant_config,
    )

    path = Path(file_path)
    if not path.exists():
        print(f"\n  Error: File not found: {path}")
        sys.exit(1)

    with open(path) as f:
        config = yaml.safe_load(f)

    # Detect file type
    filename = path.name.lower()
    if "manifest" in filename:
        result = validate_manifest(config)
        file_type = "manifest"
    elif "scoring" in filename:
        result = validate_scoring_config(config)
        file_type = "scoring"
    elif filename.endswith(".yaml") and "org_id" in config:
        result = validate_tenant_config(config)
        file_type = "tenant"
    elif "pipelines" in config:
        result = validate_manifest(config)
        file_type = "manifest"
    elif "dimensions" in config:
        result = validate_scoring_config(config)
        file_type = "scoring"
    else:
        print(f"\n  Warning: Could not detect config type for {path}")
        print(f"  Attempting manifest validation...")
        result = validate_manifest(config)
        file_type = "unknown"

    print(f"\n  KAZI OS — Config Validator")
    print(f"  ─────────────────────────")
    print(f"  File:        {path}")
    print(f"  Type:        {file_type}")
    print(f"  Status:      {'✓ valid' if result.valid else '✗ invalid'}")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"    ✗ {err}")

    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for warn in result.warnings:
            print(f"    ⚠ {warn}")

    if result.valid and not result.warnings:
        print(f"\n  No issues found.")

    print()

    if not result.valid:
        sys.exit(1)
