"""
Validation — Structured output validation and repair.

Domain-agnostic. Validates agent outputs against schemas, scores against
dimension definitions, and config files against expected structures.
Implements the Validation-Repair Loop pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repaired: bool = False
    repaired_data: Optional[Any] = None


@dataclass
class FieldSpec:
    """Specification for a single field in a schema."""
    name: str
    type: str  # "str" | "int" | "float" | "bool" | "list" | "dict"
    required: bool = True
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    choices: Optional[list] = None
    pattern: Optional[str] = None  # Regex pattern for strings


# ─── Type Coercion Map ────────────────────────────────────────────────────────

_TYPE_MAP = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
    "list": list,
    "array": list,
    "dict": dict,
    "object": dict,
}


# ─── Schema Validator ─────────────────────────────────────────────────────────


class SchemaValidator:
    """
    Validates data against a field specification schema.

    Usage:
        validator = SchemaValidator([
            FieldSpec(name="title", type="str", required=True, min_length=1),
            FieldSpec(name="score", type="float", required=True, min_value=0, max_value=10),
            FieldSpec(name="tags", type="list", required=False, default=[]),
        ])

        result = validator.validate({"title": "Test", "score": 8.5})
    """

    def __init__(self, fields: list[FieldSpec]):
        self.fields = {f.name: f for f in fields}

    def validate(self, data: dict, repair: bool = False) -> ValidationResult:
        """
        Validate data against the schema.

        Args:
            data: Dictionary to validate
            repair: If True, attempt to fix issues (coerce types, apply defaults)

        Returns:
            ValidationResult with errors, warnings, and optionally repaired data
        """
        errors = []
        warnings = []
        repaired_data = dict(data) if repair else None

        for name, spec in self.fields.items():
            value = data.get(name)

            # Check required fields
            if value is None:
                if spec.required:
                    if repair and spec.default is not None:
                        repaired_data[name] = spec.default
                        warnings.append(f"Field '{name}' missing, applied default: {spec.default}")
                    else:
                        errors.append(f"Required field '{name}' is missing")
                continue

            # Type checking and coercion
            expected_type = _TYPE_MAP.get(spec.type)
            if expected_type and not isinstance(value, expected_type):
                if repair:
                    try:
                        repaired_data[name] = expected_type(value)
                        warnings.append(
                            f"Field '{name}' coerced from {type(value).__name__} to {spec.type}"
                        )
                    except (ValueError, TypeError):
                        errors.append(
                            f"Field '{name}' expected {spec.type}, got {type(value).__name__} "
                            f"(coercion failed)"
                        )
                else:
                    errors.append(
                        f"Field '{name}' expected {spec.type}, got {type(value).__name__}"
                    )
                continue

            # Range checks (numeric)
            if spec.min_value is not None and isinstance(value, (int, float)):
                if value < spec.min_value:
                    if repair:
                        repaired_data[name] = spec.min_value
                        warnings.append(f"Field '{name}' clamped to min: {spec.min_value}")
                    else:
                        errors.append(f"Field '{name}' value {value} below minimum {spec.min_value}")

            if spec.max_value is not None and isinstance(value, (int, float)):
                if value > spec.max_value:
                    if repair:
                        repaired_data[name] = spec.max_value
                        warnings.append(f"Field '{name}' clamped to max: {spec.max_value}")
                    else:
                        errors.append(f"Field '{name}' value {value} above maximum {spec.max_value}")

            # Length checks (strings and lists)
            if spec.min_length is not None and hasattr(value, "__len__"):
                if len(value) < spec.min_length:
                    errors.append(
                        f"Field '{name}' length {len(value)} below minimum {spec.min_length}"
                    )

            if spec.max_length is not None and hasattr(value, "__len__"):
                if len(value) > spec.max_length:
                    if repair and isinstance(value, (str, list)):
                        repaired_data[name] = value[:spec.max_length]
                        warnings.append(f"Field '{name}' truncated to max length {spec.max_length}")
                    else:
                        errors.append(
                            f"Field '{name}' length {len(value)} above maximum {spec.max_length}"
                        )

            # Choice validation
            if spec.choices is not None and value not in spec.choices:
                errors.append(
                    f"Field '{name}' value '{value}' not in allowed choices: {spec.choices}"
                )

            # Regex pattern validation
            if spec.pattern is not None and isinstance(value, str):
                import re
                if not re.match(spec.pattern, value):
                    errors.append(
                        f"Field '{name}' value '{value}' does not match pattern: {spec.pattern}"
                    )

        # Check for unexpected fields
        expected_names = set(self.fields.keys())
        actual_names = set(data.keys())
        unexpected = actual_names - expected_names
        if unexpected:
            warnings.append(f"Unexpected fields: {', '.join(sorted(unexpected))}")

        valid = len(errors) == 0
        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            repaired=repair and len(warnings) > 0,
            repaired_data=repaired_data if repair else None,
        )


# ─── Validation-Repair Loop ──────────────────────────────────────────────────


async def validate_and_repair(
    data: dict,
    validator: SchemaValidator,
    repair_func: Optional[Callable] = None,
    max_attempts: int = 2,
) -> tuple[dict, ValidationResult]:
    """
    Validation-Repair Loop: validate, attempt auto-repair, optionally call
    an LLM or custom function for deeper repair.

    Args:
        data: Data to validate
        validator: Schema validator
        repair_func: Optional async function(data, errors) → repaired_data
        max_attempts: Maximum repair attempts

    Returns:
        Tuple of (final_data, final_validation_result)
    """
    for attempt in range(max_attempts):
        # First try auto-repair via schema
        result = validator.validate(data, repair=True)

        if result.valid:
            final_data = result.repaired_data or data
            if result.warnings:
                logger.info(f"Validation passed with repairs: {result.warnings}")
            return final_data, result

        # Auto-repair didn't fully fix it — try custom repair function
        if repair_func and attempt < max_attempts - 1:
            logger.info(
                f"Validation failed (attempt {attempt + 1}), "
                f"invoking repair function: {result.errors}"
            )
            data = await repair_func(result.repaired_data or data, result.errors)
        else:
            break

    # Return whatever we have with the validation result
    return result.repaired_data or data, result


# ─── Convenience Validators ───────────────────────────────────────────────────


def validate_manifest(manifest: dict) -> ValidationResult:
    """Validate a domain manifest.yaml structure."""
    validator = SchemaValidator([
        FieldSpec(name="name", type="str", required=True, min_length=1),
        FieldSpec(name="version", type="str", required=True),
        FieldSpec(name="description", type="str", required=False),
        FieldSpec(name="agents", type="list", required=True, min_length=1),
        FieldSpec(name="pipelines", type="dict", required=True),
    ])
    return validator.validate(manifest)


def validate_scoring_config(config: dict) -> ValidationResult:
    """Validate a scoring.yaml structure."""
    errors = []
    warnings = []

    dimensions = config.get("dimensions", [])
    if not dimensions:
        errors.append("No scoring dimensions defined")

    # Check weights sum to 1.0
    total_weight = sum(d.get("weight", 0) for d in dimensions)
    if abs(total_weight - 1.0) > 0.01:
        errors.append(f"Dimension weights sum to {total_weight}, expected 1.0")

    # Check tiers exist
    tiers = config.get("tiers", [])
    if not tiers:
        warnings.append("No scoring tiers defined")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_tenant_config(config: dict) -> ValidationResult:
    """Validate a tenant.yaml structure."""
    validator = SchemaValidator([
        FieldSpec(name="org_id", type="str", required=True, min_length=1),
        FieldSpec(name="name", type="str", required=True),
        FieldSpec(name="domain", type="str", required=True),
        FieldSpec(name="destinations", type="dict", required=True),
    ])
    return validator.validate(config)
