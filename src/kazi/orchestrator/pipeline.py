"""Pipeline — sequential chain of agents and human checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from kazi.agents.base import AgentContext, AgentResult, BaseAgent


@dataclass
class PipelineResult:
    """Result of a full pipeline execution.

    Attributes:
        success: True if all stages completed without failure.
        final_output: The output of the last completed stage.
        stage_results: Per-stage results in execution order.
        failed_at_stage: Index of the stage that failed, or None.
        paused_at_stage: Index of a human checkpoint awaiting approval, or None.
        status: One of "completed", "failed", "awaiting_review".
        total_duration_ms: Sum of stage durations.
        total_tokens: Sum of tokens consumed across stages.
    """

    success: bool
    final_output: dict[str, Any]
    stage_results: list[AgentResult] = field(default_factory=list)
    failed_at_stage: int | None = None
    paused_at_stage: int | None = None
    status: str = "completed"  # completed | failed | awaiting_review
    total_duration_ms: int = 0
    total_tokens: int = 0


@dataclass
class Stage:
    """A single agent stage in a pipeline.

    Wraps an agent class or instance with execution config. Stages run
    sequentially and pass their output as input to the next stage.

    Attributes:
        name: Stage identifier, used in logs and results.
        agent: Either an agent class (instantiated per run) or a pre-built
            agent instance.
        fan_out: If True, run this stage in parallel across the inputs
            named by `fan_out_key`.
        fan_out_key: Key into the payload whose value is iterable. Each
            item triggers one parallel run of the stage.
        batch: If True, the stage receives the full list of upstream
            outputs at once instead of one item.

    Example:
        Stage(name="score", agent=ScoreAgent, batch=True)
    """

    name: str
    agent: type[BaseAgent] | BaseAgent
    fan_out: bool = False
    fan_out_key: str | None = None
    batch: bool = False


@dataclass
class HumanCheckpoint:
    """A pause point that waits for human approval before continuing.

    KAZI OS does not assume any specific review destination. Products
    wire their own destination handlers (file review, dashboard approval,
    third-party app status fields, email confirmations, signed PDFs, etc.)
    and register them with the orchestrator. This dataclass only carries
    the metadata the engine needs to route the pause correctly.

    Attributes:
        name: Checkpoint identifier, used in logs and results.
        destination: Key into the registry of destination handlers. The
            product is responsible for registering a handler under this key.
        config: Destination-specific settings, passed verbatim to the
            handler. KAZI OS does not interpret the contents.
        trigger_on: The value the destination should report when the
            checkpoint is resolved. Semantics are destination-specific.
        timeout_hours: Optional. If set, the pipeline will mark the job
            as failed after this many hours of waiting.

    Example:
        HumanCheckpoint(
            name="approve_draft",
            destination="dashboard",
            config={"queue": "drafts", "reviewer": "default"},
            trigger_on="approved",
            timeout_hours=72,
        )
    """

    name: str
    destination: str
    config: dict[str, Any] = field(default_factory=dict)
    trigger_on: str = "approved"
    timeout_hours: int | None = None


# Type alias for what can appear in a pipeline's stage list.

PipelineStep = Union[Stage, HumanCheckpoint, BaseAgent]


class Pipeline:
    """Sequential chain of stages and checkpoints.

    A pipeline executes its steps in order. Each step's output becomes the
    next step's input. If a step is a HumanCheckpoint, the pipeline pauses
    and returns a PipelineResult with status="awaiting_review". The
    pipeline can be resumed later by calling `resume()` with the same
    context and the index of the paused stage.

    Example:
        pipeline = Pipeline(
            name="weekly-brief",
            stages=[
                Stage(name="discover", agent=DiscoverAgent),
                Stage(name="rank", agent=RankAgent, batch=True),
                HumanCheckpoint(
                    name="approve_picks",
                    destination="dashboard",
                ),
                Stage(name="publish", agent=PublishAgent),
            ],
        )
        result = await pipeline.run({"topic": "..."}, context)
    """

    def __init__(
        self,
        name: str,
        stages: list[PipelineStep] | None = None,
    ):
        self.name = name
        self.stages: list[PipelineStep] = stages or []

    def add_stage(self, step: PipelineStep, position: int = -1) -> None:
        """Insert a stage or checkpoint at a specific position.

        Args:
            step: A Stage, HumanCheckpoint, or raw BaseAgent.
            position: Insert index. -1 appends to the end.
        """
        if position == -1:
            self.stages.append(step)
        else:
            self.stages.insert(position, step)

    async def run(
        self,
        initial_input: dict,
        context: AgentContext,
        start_at: int = 0,
    ) -> PipelineResult:
        """Execute stages sequentially from `start_at` to the end.

        Pauses on HumanCheckpoint by returning a result with
        status="awaiting_review" and paused_at_stage set to the
        checkpoint's index. The caller is responsible for resuming
        execution once the checkpoint is resolved.

        Args:
            initial_input: The payload for the first stage being run.
                When resuming, this should be the output of the stage
                immediately before the resumption point.
            context: Shared execution context.
            start_at: Index to begin execution from. Use 0 for a fresh
                run, or `paused_at_stage + 1` to resume after a checkpoint.

        Returns:
            A PipelineResult describing the outcome.
        """
        current_input = initial_input
        stage_results: list[AgentResult] = []
        total_tokens = 0

        for i in range(start_at, len(self.stages)):
            step = self.stages[i]

            # Human checkpoint: pause the pipeline and return.
            if isinstance(step, HumanCheckpoint):
                return PipelineResult(
                    success=True,
                    final_output=current_input,
                    stage_results=stage_results,
                    paused_at_stage=i,
                    status="awaiting_review",
                    total_duration_ms=sum(r.duration_ms for r in stage_results),
                    total_tokens=total_tokens,
                )

            # Agent stage: run it.
            agent = self._instantiate(step)
            result = await agent.run(current_input, context)
            stage_results.append(result)
            total_tokens += result.tokens_used

            if not result.success:
                return PipelineResult(
                    success=False,
                    final_output=result.data,
                    stage_results=stage_results,
                    failed_at_stage=i,
                    status="failed",
                    total_duration_ms=sum(r.duration_ms for r in stage_results),
                    total_tokens=total_tokens,
                )

            current_input = result.data

        return PipelineResult(
            success=True,
            final_output=current_input,
            stage_results=stage_results,
            status="completed",
            total_duration_ms=sum(r.duration_ms for r in stage_results),
            total_tokens=total_tokens,
        )

    async def resume(
        self,
        approved_input: dict,
        context: AgentContext,
        paused_at_stage: int,
    ) -> PipelineResult:
        """Resume execution after a human checkpoint is resolved.

        Args:
            approved_input: The payload to feed to the stage immediately
                after the checkpoint. Usually the same payload that was
                in `final_output` when the pipeline paused, possibly
                edited during human review.
            context: Shared execution context.
            paused_at_stage: The index returned in the paused result.

        Returns:
            A PipelineResult describing the outcome from the resumption
            point to the end of the pipeline.
        """
        return await self.run(
            initial_input=approved_input,
            context=context,
            start_at=paused_at_stage + 1,
        )

    def _instantiate(self, step: PipelineStep) -> BaseAgent:
        """Return a BaseAgent ready to run, regardless of how it was declared."""
        # Already an instance.
        if isinstance(step, BaseAgent):
            return step

        # Wrapped in a Stage.
        if isinstance(step, Stage):
            agent = step.agent
            if isinstance(agent, BaseAgent):
                return agent
            if isinstance(agent, type) and issubclass(agent, BaseAgent):
                return agent()
            raise TypeError(
                f"Stage '{step.name}' agent must be a BaseAgent class or instance, "
                f"got {type(agent).__name__}"
            )

        raise TypeError(
            f"Unsupported pipeline step type: {type(step).__name__}"
        )

    def __repr__(self) -> str:
        step_names = []
        for s in self.stages:
            if isinstance(s, HumanCheckpoint):
                step_names.append(f"[review:{s.name}]")
            elif isinstance(s, Stage):
                step_names.append(s.name)
            else:
                step_names.append(getattr(s, "name", type(s).__name__))
        return f"Pipeline('{self.name}': {' → '.join(step_names)})"