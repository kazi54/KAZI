"""FanOut — parallel execution of a pipeline across multiple inputs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from kazi.agents.base import AgentContext
from kazi.orchestrator.pipeline import Pipeline, PipelineResult


@dataclass
class FanOutResult:
    """Aggregated result from parallel pipeline executions."""

    success: bool
    results: list[PipelineResult]
    succeeded: int = 0
    failed: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0


class FanOut:
    """Parallel execution of the same pipeline across multiple inputs.

    This is the swarm pattern — one pipeline, many inputs, concurrent execution.

    Example:
        fan_out = FanOut(pipeline=weekly_brief_pipeline, max_concurrency=5)
        result = await fan_out.run(
            inputs=[{"researcher_id": r} for r in researcher_ids],
            context=context
        )
    """

    def __init__(self, pipeline: Pipeline, max_concurrency: int = 10):
        self.pipeline = pipeline
        self.max_concurrency = max_concurrency

    async def run(self, inputs: list[dict], context: AgentContext) -> FanOutResult:
        """Execute the pipeline for each input in parallel (bounded concurrency)."""
        semaphore = asyncio.Semaphore(self.max_concurrency)
        results: list[PipelineResult] = []

        async def run_one(input_data: dict) -> PipelineResult:
            async with semaphore:
                return await self.pipeline.run(input_data, context)

        tasks = [run_one(inp) for inp in inputs]
        results = await asyncio.gather(*tasks)

        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded

        return FanOutResult(
            success=failed == 0,
            results=list(results),
            succeeded=succeeded,
            failed=failed,
            total_duration_ms=sum(r.total_duration_ms for r in results),
            total_tokens=sum(r.total_tokens for r in results),
        )

    def __repr__(self) -> str:
        return f"FanOut(pipeline='{self.pipeline.name}', max_concurrency={self.max_concurrency})"
