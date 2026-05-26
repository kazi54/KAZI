"""
State Store — Pipeline run persistence engine.

Domain-agnostic. Persists pipeline run state, stage results, checkpoint
states, and decision logs. Supports file-based (JSON) and pluggable
backends (SQLite, PostgreSQL, etc.).

Responsibilities:
  - Save/load pipeline run state (for retry, render, audit)
  - Save/load checkpoint states (for HITL processor)
  - Query run history (by org_id, pipeline, date range, status)
  - Decision log (every scoring decision, every checkpoint resolution)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class StageResult:
    """Result of a single pipeline stage execution."""
    stage_name: str
    agent_name: Optional[str]
    status: str  # "success" | "failure" | "skipped"
    started_at: str
    completed_at: str
    duration_ms: int
    output_payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


@dataclass
class PipelineRun:
    """Complete state of a pipeline execution."""
    run_id: str
    pipeline_name: str
    org_id: str
    status: str  # "pending" | "running" | "paused" | "completed" | "failed"
    input_payload: dict
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    current_stage: int = 0
    stages: list[StageResult] = field(default_factory=list)
    output_payload: dict = field(default_factory=dict)
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DecisionEntry:
    """A logged decision (scoring, checkpoint resolution, routing)."""
    run_id: str
    org_id: str
    timestamp: str
    decision_type: str  # "score" | "checkpoint" | "route" | "retry"
    context: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)


# ─── Abstract Backend ─────────────────────────────────────────────────────────


class StateBackend(ABC):
    """Abstract interface for state persistence backends."""

    @abstractmethod
    async def save_run(self, run: PipelineRun) -> None: ...

    @abstractmethod
    async def load_run(self, run_id: str) -> Optional[PipelineRun]: ...

    @abstractmethod
    async def query_runs(
        self,
        org_id: Optional[str] = None,
        pipeline_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[PipelineRun]: ...

    @abstractmethod
    async def save_checkpoint(self, checkpoint) -> None: ...

    @abstractmethod
    async def load_checkpoint(self, run_id: str): ...

    @abstractmethod
    async def load_all_pending_checkpoints(self) -> list: ...

    @abstractmethod
    async def load_tenant_destination_config(
        self, org_id: str, destination_key: str
    ) -> Optional[dict]: ...

    @abstractmethod
    async def log_decision(self, entry: DecisionEntry) -> None: ...

    @abstractmethod
    async def query_decisions(
        self, run_id: Optional[str] = None, org_id: Optional[str] = None, limit: int = 100
    ) -> list[DecisionEntry]: ...


# ─── File-Based Backend (default) ─────────────────────────────────────────────


class FileStateBackend(StateBackend):
    """
    JSON file-based state persistence.

    Structure:
        .kazi-state/
        ├── runs/
        │   ├── run_2026-05-26_001.json
        │   └── run_2026-05-26_002.json
        ├── checkpoints/
        │   └── run_2026-05-26_001.json
        └── decisions/
            └── 2026-05-26.jsonl
    """

    def __init__(self, base_dir: str = ".kazi-state"):
        self._base = Path(base_dir)
        self._runs_dir = self._base / "runs"
        self._checkpoints_dir = self._base / "checkpoints"
        self._decisions_dir = self._base / "decisions"

        # Create directories
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._decisions_dir.mkdir(parents=True, exist_ok=True)

    async def save_run(self, run: PipelineRun) -> None:
        path = self._runs_dir / f"{run.run_id}.json"
        data = asdict(run)
        path.write_text(json.dumps(data, indent=2, default=str))
        logger.debug(f"Saved run state: {run.run_id} ({run.status})")

    async def load_run(self, run_id: str) -> Optional[PipelineRun]:
        path = self._runs_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return PipelineRun(
            run_id=data["run_id"],
            pipeline_name=data["pipeline_name"],
            org_id=data["org_id"],
            status=data["status"],
            input_payload=data["input_payload"],
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            duration_ms=data.get("duration_ms"),
            current_stage=data.get("current_stage", 0),
            stages=[StageResult(**s) for s in data.get("stages", [])],
            output_payload=data.get("output_payload", {}),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )

    async def query_runs(
        self,
        org_id: Optional[str] = None,
        pipeline_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[PipelineRun]:
        runs = []
        for path in sorted(self._runs_dir.glob("*.json"), reverse=True):
            if len(runs) >= limit:
                break
            data = json.loads(path.read_text())
            if org_id and data.get("org_id") != org_id:
                continue
            if pipeline_name and data.get("pipeline_name") != pipeline_name:
                continue
            if status and data.get("status") != status:
                continue
            runs.append(await self.load_run(data["run_id"]))
        return runs

    async def save_checkpoint(self, checkpoint) -> None:
        path = self._checkpoints_dir / f"{checkpoint.run_id}.json"
        data = asdict(checkpoint) if hasattr(checkpoint, "__dataclass_fields__") else vars(checkpoint)
        # Convert enums and datetimes to strings
        path.write_text(json.dumps(data, indent=2, default=str))

    async def load_checkpoint(self, run_id: str):
        path = self._checkpoints_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    async def load_all_pending_checkpoints(self) -> list:
        pending = []
        for path in self._checkpoints_dir.glob("*.json"):
            data = json.loads(path.read_text())
            if data.get("resolution") == "pending":
                pending.append(data)
        return pending

    async def load_tenant_destination_config(
        self, org_id: str, destination_key: str
    ) -> Optional[dict]:
        """
        Load destination config for a tenant.
        Delegates to TenantConfig loader — the store just provides the interface.
        """
        # This will be wired to TenantConfig at platform init
        return self._tenant_configs.get(org_id, {}).get(destination_key)

    def register_tenant_configs(self, configs: dict) -> None:
        """Register resolved tenant destination configs for HITL polling."""
        self._tenant_configs = configs

    async def log_decision(self, entry: DecisionEntry) -> None:
        date_str = entry.timestamp[:10]  # "2026-05-26"
        path = self._decisions_dir / f"{date_str}.jsonl"
        data = asdict(entry)
        with open(path, "a") as f:
            f.write(json.dumps(data, default=str) + "\n")

    async def query_decisions(
        self, run_id: Optional[str] = None, org_id: Optional[str] = None, limit: int = 100
    ) -> list[DecisionEntry]:
        entries = []
        for path in sorted(self._decisions_dir.glob("*.jsonl"), reverse=True):
            if len(entries) >= limit:
                break
            for line in reversed(path.read_text().strip().split("\n")):
                if len(entries) >= limit:
                    break
                data = json.loads(line)
                if run_id and data.get("run_id") != run_id:
                    continue
                if org_id and data.get("org_id") != org_id:
                    continue
                entries.append(DecisionEntry(**data))
        return entries


# ─── Store Factory ────────────────────────────────────────────────────────────


def create_state_store(backend: str = "file", **kwargs) -> StateBackend:
    """
    Factory for creating state store backends.

    Supported backends:
      - "file" (default): JSON files in .kazi-state/
      - "sqlite": SQLite database (future)
      - "postgres": PostgreSQL (future)
    """
    if backend == "file":
        base_dir = kwargs.get("base_dir", ".kazi-state")
        return FileStateBackend(base_dir=base_dir)
    else:
        raise ValueError(f"Unsupported state backend: {backend}. Available: file")
