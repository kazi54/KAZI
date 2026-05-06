"""Base agent classes — the fundamental unit of work in KAZI."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Shared context passed to agents during execution.

    Contains references to LLM clients, database connections,
    and any shared state needed across the pipeline.
    """

    job_id: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    product: str | None = None
    tools: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Structured output from an agent execution."""

    success: bool
    data: dict[str, Any]
    confidence: float = 1.0  # 0.0 to 1.0
    tokens_used: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """The fundamental unit of work in KAZI.

    Every agent answers one question and produces a structured output.
    Subclass this to create domain-specific agents.

    Example:
        class MyScoutAgent(BaseAgent):
            name = "my-scout"
            version = "0.1.0"
            input_schema = {"type": "object", "properties": {"query": {"type": "string"}}}
            output_schema = {"type": "object", "properties": {"results": {"type": "array"}}}

            async def execute(self, input: dict, context: AgentContext) -> AgentResult:
                results = await self.search(input["query"])
                return AgentResult(success=True, data={"results": results})
    """

    name: str = "base-agent"
    version: str = "0.1.0"
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}

    async def run(self, input: dict, context: AgentContext) -> AgentResult:
        """Execute the agent with validation and timing. Do not override this."""
        start = time.perf_counter_ns()

        # Validate input
        if not await self.validate_input(input):
            return AgentResult(
                success=False,
                data={},
                errors=[f"Input validation failed for {self.name}"],
            )

        # Execute core logic
        result = await self.execute(input, context)

        # Record timing
        result.duration_ms = (time.perf_counter_ns() - start) // 1_000_000

        # Validate output
        if result.success and not await self.validate_output(result.data):
            result.success = False
            result.errors.append(f"Output validation failed for {self.name}")

        return result

    @abstractmethod
    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        """Core agent logic. Must be implemented by subclasses."""
        raise NotImplementedError

    async def validate_input(self, input: dict) -> bool:
        """Validate input against input_schema. Override for custom validation."""
        # Basic presence check — override for JSON schema validation
        return isinstance(input, dict)

    async def validate_output(self, output: dict) -> bool:
        """Validate output against output_schema. Override for custom validation."""
        return isinstance(output, dict)


class BaseScoutAgent(BaseAgent):
    """Agent specialized for data ingestion and discovery.

    Crawls external sources, normalizes data, and returns structured results.
    """

    name = "base-scout"

    @abstractmethod
    async def crawl(self, query: dict, context: AgentContext) -> list[dict]:
        """Crawl data sources and return raw results."""
        raise NotImplementedError

    async def normalize(self, raw_results: list[dict]) -> list[dict]:
        """Normalize raw results into a standard format. Override to customize."""
        return raw_results

    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        """Scout pattern: crawl → normalize → return."""
        raw = await self.crawl(input, context)
        normalized = await self.normalize(raw)
        return AgentResult(
            success=True,
            data={"results": normalized, "count": len(normalized)},
        )


class BaseScoreAgent(BaseAgent):
    """Agent specialized for multi-dimensional evaluation.

    Scores an entity against a profile using configurable dimensions.
    """

    name = "base-score"

    @abstractmethod
    async def score(self, entity: dict, context: AgentContext) -> dict[str, float]:
        """Score an entity. Returns dimension_name → score (0-100) mapping."""
        raise NotImplementedError

    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        """Score pattern: score → aggregate → classify."""
        scores = await self.score(input, context)
        overall = sum(scores.values()) / len(scores) if scores else 0
        return AgentResult(
            success=True,
            data={"scores": scores, "overall": overall},
            confidence=min(scores.values()) / 100 if scores else 0,
        )


class BaseProfileAgent(BaseAgent):
    """Agent specialized for entity/identity management.

    Builds and maintains structured profiles from various data sources.
    """

    name = "base-profile"

    @abstractmethod
    async def build_profile(self, input: dict, context: AgentContext) -> dict:
        """Build or update a profile from input data."""
        raise NotImplementedError

    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        """Profile pattern: gather → structure → return."""
        profile = await self.build_profile(input, context)
        return AgentResult(success=True, data={"profile": profile})


class BaseCompileAgent(BaseAgent):
    """Agent specialized for synthesis and report assembly.

    Takes outputs from previous agents and compiles them into deliverables.
    """

    name = "base-compile"

    @abstractmethod
    async def compile(self, inputs: list[dict], context: AgentContext) -> dict:
        """Compile multiple inputs into a single deliverable."""
        raise NotImplementedError

    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        """Compile pattern: gather inputs → synthesize → format."""
        # Input expected to have a "sources" key with list of prior agent outputs
        sources = input.get("sources", [input])
        compiled = await self.compile(sources, context)
        return AgentResult(success=True, data={"deliverable": compiled})
