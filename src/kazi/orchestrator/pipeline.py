"""Pipeline — sequential chain of agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kazi.agents.base import AgentContext, AgentResult, BaseAgent


@dataclass
class PipelineResult:
    """Result of a full pipeline execution."""

    success: bool
    final_output: dict[str, Any]
    stage_results: list[AgentResult] = field(default_factory=list)
    failed_at_stage: int | None = None
    total_duration_ms: int = 0
    total_tokens: int = 0


class Pipeline:
    """Sequential chain of agents where each agent's output feeds the next.

    Example:
        pipeline = Pipeline(
            name="patent-audit",
            stages=[ScoutAgent(), ScoreAgent(), CompileAgent()]
        )
        result = await pipeline.run({"patent_number": "US12345"}, context)
    """

    def __init__(self, name: str, stages: list[BaseAgent] | None = None):
        self.name = name
        self.stages: list[BaseAgent] = stages or []

    def add_stage(self, agent: BaseAgent, position: int = -1) -> None:
        """Insert an agent at a specific position. -1 appends to end."""
        if position == -1:
            self.stages.append(agent)
        else:
            self.stages.insert(position, agent)

    async def run(self, initial_input: dict, context: AgentContext) -> PipelineResult:
        """Execute stages sequentially, passing output → input between stages."""
        current_input = initial_input
        stage_results: list[AgentResult] = []
        total_tokens = 0

        for i, agent in enumerate(self.stages):
            result = await agent.run(current_input, context)
            stage_results.append(result)
            total_tokens += result.tokens_used

            if not result.success:
                return PipelineResult(
                    success=False,
                    final_output=result.data,
                    stage_results=stage_results,
                    failed_at_stage=i,
                    total_duration_ms=sum(r.duration_ms for r in stage_results),
                    total_tokens=total_tokens,
                )

            # Pass output as input to next stage
            current_input = result.data

        return PipelineResult(
            success=True,
            final_output=current_input,
            stage_results=stage_results,
            total_duration_ms=sum(r.duration_ms for r in stage_results),
            total_tokens=total_tokens,
        )

    def __repr__(self) -> str:
        stage_names = " → ".join(s.name for s in self.stages)
        return f"Pipeline('{self.name}': {stage_names})"
