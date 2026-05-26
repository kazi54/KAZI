"""
HITL Processor — Human-in-the-Loop checkpoint resolution engine.

Domain-agnostic. Polls destinations for status changes, receives webhook
signals, or accepts CLI/API input to resume paused pipelines.

Resolution sources:
  1. Polling — periodically check destination adapter's check_status()
  2. Webhook — external system POSTs to /api/checkpoints/{run_id}/resolve
  3. CLI/API — operator manually approves/rejects via kazi resume
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


class Resolution(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class CheckpointState:
    """Represents a paused checkpoint waiting for resolution."""
    run_id: str
    pipeline_name: str
    checkpoint_name: str
    org_id: str
    receipt_id: str
    destination_key: str
    paused_at: datetime
    resolution: Resolution = Resolution.PENDING
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    reason: Optional[str] = None
    payload: dict = field(default_factory=dict)


# Type alias for the callback that resumes a pipeline
ResumeCallback = Callable[[str, Resolution, Optional[str]], Awaitable[None]]


class HITLProcessor:
    """
    Manages pending checkpoints and resolves them through multiple channels.

    Usage:
        processor = HITLProcessor(state_store=store, destination_registry=registry)
        processor.on_resume(resume_callback)
        await processor.register(checkpoint_state)
        await processor.start_polling(interval=60)
    """

    def __init__(self, state_store, destination_registry):
        self._store = state_store
        self._destinations = destination_registry
        self._pending: dict[str, CheckpointState] = {}
        self._resume_callback: Optional[ResumeCallback] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._poll_interval: int = 60

    def on_resume(self, callback: ResumeCallback) -> None:
        """Register the callback invoked when a checkpoint resolves."""
        self._resume_callback = callback

    async def register(self, state: CheckpointState) -> None:
        """Register a new pending checkpoint for resolution tracking."""
        self._pending[state.run_id] = state
        await self._store.save_checkpoint(state)
        logger.info(
            f"Checkpoint registered: {state.pipeline_name}/{state.checkpoint_name} "
            f"[{state.org_id}] run={state.run_id}"
        )

    async def resolve(
        self,
        run_id: str,
        resolution: Resolution,
        resolved_by: str = "system",
        reason: Optional[str] = None,
    ) -> None:
        """
        Resolve a checkpoint (from any source: poll, webhook, CLI).
        Triggers the resume callback to continue pipeline execution.
        """
        state = self._pending.get(run_id)
        if state is None:
            # Try loading from persistent store
            state = await self._store.load_checkpoint(run_id)
            if state is None:
                raise ValueError(f"No pending checkpoint for run_id={run_id}")

        state.resolution = resolution
        state.resolved_at = datetime.utcnow()
        state.resolved_by = resolved_by
        state.reason = reason

        await self._store.save_checkpoint(state)
        self._pending.pop(run_id, None)

        logger.info(
            f"Checkpoint resolved: {state.pipeline_name}/{state.checkpoint_name} "
            f"[{state.org_id}] → {resolution.value} by {resolved_by}"
        )

        if self._resume_callback:
            await self._resume_callback(run_id, resolution, reason)

    async def start_polling(self, interval: int = 60) -> None:
        """Start background polling of destination adapters for status changes."""
        self._poll_interval = interval
        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info(f"HITL polling started (interval={interval}s)")

    async def stop_polling(self) -> None:
        """Stop the background polling task."""
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
            self._polling_task = None
            logger.info("HITL polling stopped")

    async def _poll_loop(self) -> None:
        """Poll all pending checkpoints for status changes."""
        while True:
            try:
                await self._poll_all()
            except Exception as e:
                logger.error(f"HITL poll error: {e}")
            await asyncio.sleep(self._poll_interval)

    async def _poll_all(self) -> None:
        """Check each pending checkpoint's destination for resolution."""
        for run_id, state in list(self._pending.items()):
            try:
                adapter = self._destinations.get(state.destination_key)
                if adapter is None:
                    continue

                # Load tenant destination config from store
                tenant_config = await self._store.load_tenant_destination_config(
                    state.org_id, state.destination_key
                )
                if tenant_config is None:
                    continue

                status = await adapter.check_status(state.receipt_id, tenant_config)

                if status == "approved":
                    await self.resolve(run_id, Resolution.APPROVED, resolved_by="poll")
                elif status == "rejected":
                    await self.resolve(run_id, Resolution.REJECTED, resolved_by="poll")
                # "pending" → do nothing, check again next cycle

            except Exception as e:
                logger.warning(
                    f"Poll failed for {run_id} ({state.destination_key}): {e}"
                )

    async def load_pending(self) -> None:
        """Load all pending checkpoints from persistent store on startup."""
        pending = await self._store.load_all_pending_checkpoints()
        for state in pending:
            self._pending[state.run_id] = state
        logger.info(f"Loaded {len(pending)} pending checkpoints from store")

    def get_pending(self, org_id: Optional[str] = None) -> list[CheckpointState]:
        """List pending checkpoints, optionally filtered by tenant."""
        if org_id:
            return [s for s in self._pending.values() if s.org_id == org_id]
        return list(self._pending.values())
