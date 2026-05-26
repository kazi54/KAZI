"""Pipeline Builder — constructs Pipeline objects from manifest YAML definitions.

Reads the `pipelines:` section of a domain manifest and produces registered,
runnable Pipeline instances. This is the bridge between declarative config
(manifest.yaml) and runtime execution (Pipeline + Orchestrator).

Usage:
    from kazi.orchestrator.builder import PipelineBuilder

    builder = PipelineBuilder(agent_registry=registry)
    pipelines = builder.from_manifest(manifest_data, domain_path)

    for pipeline in pipelines:
        orchestrator.register_pipeline(pipeline)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kazi.agents.base import BaseAgent
from kazi.orchestrator.pipeline import (
    HumanCheckpoint,
    Pipeline,
    PipelineStep,
    Stage,
)
from kazi.orchestrator.orchestrator import (
    EventTrigger,
    OnDemandTrigger,
    ScheduledTrigger,
    Trigger,
    TriggerType,
)


@dataclass
class PipelineDefinition:
    """Parsed pipeline definition from a manifest.

    Intermediate representation between raw YAML and a runnable Pipeline.
    """

    name: str
    description: str
    stages: list[dict[str, Any]]
    trigger: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None
    hitl: dict[str, Any] | None = None


@dataclass
class BuildResult:
    """Result of building pipelines from a manifest.

    Attributes:
        pipelines: Successfully built Pipeline objects.
        triggers: Trigger objects associated with the pipelines.
        errors: Any errors encountered during building.
    """

    pipelines: list[Pipeline] = field(default_factory=list)
    triggers: list[Trigger] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PipelineBuilder:
    """Builds Pipeline objects from manifest YAML definitions.

    Requires an agent registry to resolve agent names to classes/instances.
    The registry is a dict mapping agent_name → BaseAgent class or instance.

    Example:
        registry = {
            "market_scout": MarketScout,
            "relevance_scorer": RelevanceScorer,
            "brief_compiler": BriefCompiler,
        }
        builder = PipelineBuilder(agent_registry=registry)
        result = builder.from_manifest(manifest_data)
    """

    def __init__(self, agent_registry: dict[str, type[BaseAgent] | BaseAgent]):
        self._registry = agent_registry

    def from_manifest(self, manifest: dict[str, Any]) -> BuildResult:
        """Build all pipelines defined in a manifest.

        Args:
            manifest: Parsed YAML manifest (the full dict, not just pipelines section).

        Returns:
            BuildResult with pipelines, triggers, and any errors.
        """
        result = BuildResult()
        pipelines_data = manifest.get("pipelines", {})

        if not pipelines_data:
            return result

        for pipeline_name, pipeline_config in pipelines_data.items():
            try:
                pipeline = self._build_pipeline(pipeline_name, pipeline_config)
                result.pipelines.append(pipeline)

                # Build trigger if defined
                trigger = self._build_trigger(pipeline_name, pipeline_config)
                if trigger:
                    result.triggers.append(trigger)

            except Exception as e:
                result.errors.append(
                    f"Failed to build pipeline '{pipeline_name}': {e}"
                )

        return result

    def _build_pipeline(self, name: str, config: dict[str, Any]) -> Pipeline:
        """Build a single Pipeline from its config block.

        Args:
            name: Pipeline name (the YAML key).
            config: The pipeline's configuration dict.

        Returns:
            A runnable Pipeline instance.

        Raises:
            ValueError: If a referenced agent is not in the registry.
        """
        stages_config = config.get("stages", [])
        hitl_config = config.get("hitl", {})
        delivery_config = config.get("delivery", {})

        steps: list[PipelineStep] = []

        for stage_def in stages_config:
            agent_name = stage_def["agent"]

            # Resolve agent from registry
            agent_cls = self._registry.get(agent_name)
            if agent_cls is None:
                raise ValueError(
                    f"Agent '{agent_name}' not found in registry. "
                    f"Available: {list(self._registry.keys())}"
                )

            # Build Stage with options
            stage = Stage(
                name=agent_name,
                agent=agent_cls,
                fan_out=stage_def.get("fan_out", False),
                fan_out_key=stage_def.get("fan_out_key"),
                batch=stage_def.get("batch", False),
            )
            steps.append(stage)

            # Insert human checkpoint after this stage if configured
            if self._needs_checkpoint(agent_name, hitl_config):
                checkpoint = self._build_checkpoint(agent_name, hitl_config)
                steps.append(checkpoint)

        # If delivery is configured, it implies a final destination push.
        # The product layer handles this — we just record it as metadata.
        pipeline = Pipeline(name=name, stages=steps)

        # Attach delivery config as metadata for the product layer to read
        pipeline._delivery_config = delivery_config  # type: ignore[attr-defined]

        return pipeline

    def _build_trigger(
        self, pipeline_name: str, config: dict[str, Any]
    ) -> Trigger | None:
        """Build a Trigger from the pipeline's trigger config.

        Returns None if no trigger is defined (defaults to on-demand).
        """
        trigger_config = config.get("trigger")
        if not trigger_config:
            # Default: on-demand trigger
            return OnDemandTrigger(
                name=f"{pipeline_name}-on-demand",
                pipeline_name=pipeline_name,
            )

        trigger_type = trigger_config.get("type", "on_demand")

        if trigger_type == "scheduled":
            cron = trigger_config.get("cron", "0 6 * * 1")
            return ScheduledTrigger(
                name=f"{pipeline_name}-scheduled",
                pipeline_name=pipeline_name,
                cron=cron,
                fan_out_source=trigger_config.get("fan_out_source"),
            )

        elif trigger_type == "event":
            return EventTrigger(
                name=f"{pipeline_name}-event",
                pipeline_name=pipeline_name,
                event=trigger_config.get("event", ""),
                condition=None,  # Condition parsing is product-specific
            )

        else:
            return OnDemandTrigger(
                name=f"{pipeline_name}-on-demand",
                pipeline_name=pipeline_name,
            )

    def _needs_checkpoint(self, agent_name: str, hitl_config: dict) -> bool:
        """Determine if a human checkpoint should follow this agent.

        HITL config can specify:
          - policy: "after_every_stage" | "on_high_score" | "before_delivery" | "manual"
          - after_stages: ["agent_name_1", "agent_name_2"]
        """
        if not hitl_config:
            return False

        # Explicit list of stages that need review
        after_stages = hitl_config.get("after_stages", [])
        if agent_name in after_stages:
            return True

        return False

    def _build_checkpoint(
        self, after_agent: str, hitl_config: dict
    ) -> HumanCheckpoint:
        """Build a HumanCheckpoint for insertion after a specific agent."""
        destination = hitl_config.get("destination", "review")
        timeout = hitl_config.get("timeout_hours", 72)

        return HumanCheckpoint(
            name=f"review-after-{after_agent}",
            destination=destination,
            config={"triggered_by": after_agent},
            trigger_on="approved",
            timeout_hours=timeout,
        )
