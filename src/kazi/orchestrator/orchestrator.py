"""Orchestrator — central coordinator that dispatches jobs to pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from kazi.agents.base import AgentContext
from kazi.orchestrator.pipeline import Pipeline, PipelineResult
from kazi.orchestrator.fanout import FanOut, FanOutResult


class TriggerType(str, Enum):
    ON_DEMAND = "on_demand"
    SCHEDULED = "scheduled"
    EVENT = "event"


@dataclass
class Trigger:
    """Base trigger definition."""

    name: str
    pipeline_name: str
    trigger_type: TriggerType= TriggerType.ON_DEMAND
    


@dataclass
class OnDemandTrigger(Trigger):
    """Fires when explicitly requested by a user or system call."""

    trigger_type: TriggerType = TriggerType.ON_DEMAND


@dataclass
class ScheduledTrigger(Trigger):
    """Fires on a cron schedule."""

    cron: str = "0 2 * * 1"  # Default: Monday 2 AM
    fan_out_source: str | None = None  # Function/query to get parallel inputs
    trigger_type: TriggerType = TriggerType.SCHEDULED


@dataclass
class EventTrigger(Trigger):
    """Fires when a system event matches a condition."""

    event: str = ""
    condition: Callable[[Any], bool] | None = None
    trigger_type: TriggerType = TriggerType.EVENT


@dataclass
class Job:
    """A unit of work dispatched by the orchestrator."""

    id: str
    pipeline_name: str
    trigger_type: TriggerType
    payload: dict[str, Any]
    status: str = "queued"  # queued → running → completed | failed | review
    result: PipelineResult | FanOutResult | None = None


class Orchestrator:
    """Central coordinator that dispatches jobs to pipelines.

    Example:
        orch = Orchestrator()
        orch.register_pipeline(brief_pipeline)
        orch.register_trigger(OnDemandTrigger(name="run-brief", pipeline_name="weekly-brief"))

        result = await orch.dispatch(Job(
            id="job-001",
            pipeline_name="weekly-brief",
            trigger_type=TriggerType.ON_DEMAND,
            payload={"industry": "electric-vehicles"}
        ))
    """

    def __init__(self):
        self.pipelines: dict[str, Pipeline] = {}
        self.triggers: list[Trigger] = []
        self.fan_outs: dict[str, FanOut] = {}

    def register_pipeline(self, pipeline: Pipeline) -> None:
        """Register a pipeline by name."""
        self.pipelines[pipeline.name] = pipeline

    def register_trigger(self, trigger: Trigger) -> None:
        """Register a trigger."""
        self.triggers.append(trigger)

    def register_fan_out(self, name: str, fan_out: FanOut) -> None:
        """Register a fan-out configuration."""
        self.fan_outs[name] = fan_out

    async def dispatch(self, job: Job, context: AgentContext | None = None) -> Job:
        """Route a job to the appropriate pipeline and execute."""
        if context is None:
            context = AgentContext(job_id=job.id)

        pipeline = self.pipelines.get(job.pipeline_name)
        if not pipeline:
            job.status = "failed"
            return job

        job.status = "running"

        try:
            result = await pipeline.run(job.payload, context)
            job.result = result
            job.status = "completed" if result.success else "failed"
        except Exception as e:
            job.status = "failed"
            job.result = PipelineResult(
                success=False,
                final_output={"error": str(e)},
            )

        return job

    async def fan_out(
        self, fan_out_name: str, inputs: list[dict], context: AgentContext
    ) -> FanOutResult:
        """Execute a registered fan-out across multiple inputs."""
        fan_out = self.fan_outs.get(fan_out_name)
        if not fan_out:
            raise ValueError(f"FanOut '{fan_out_name}' not registered")
        return await fan_out.run(inputs, context)

    def __repr__(self) -> str:
        return (
            f"Orchestrator(pipelines={list(self.pipelines.keys())}, "
            f"triggers={len(self.triggers)})"
        )
