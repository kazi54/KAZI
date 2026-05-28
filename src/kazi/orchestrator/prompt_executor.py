"""Prompt-Driven Agent Executor — runs pipelines defined entirely in YAML.

This is the key module that makes KAZI OS user-driven. Instead of requiring
users to write Python agent classes, they define agents as:
  - role (who the agent is)
  - goal (what it produces)
  - instructions (how it should think)

The executor reads the domain's YAML files (identity, voice, guardrails, council)
and constructs LLM calls for each pipeline stage automatically.

Usage:
    from kazi.orchestrator.prompt_executor import PromptExecutor

    executor = PromptExecutor(domain_dir=Path("./my-domain"))
    result = await executor.run("weekly-post", {"topic": "Leadership transitions"})
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from kazi.utils.llm import (
    BaseLLMClient,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    create_llm_client,
)

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    agent: str
    output: str
    tokens_used: int = 0
    passed_guardrails: bool = True
    council_feedback: Optional[dict] = None


@dataclass
class PipelineResult:
    """Result from a full pipeline run."""
    pipeline: str
    status: str  # "completed" | "failed" | "guardrail_failed"
    final_output: str = ""
    stages: list[StageResult] = field(default_factory=list)
    total_tokens: int = 0
    model: str = ""


class DomainContext:
    """Loads and holds all YAML context files for a domain."""

    def __init__(self, domain_dir: Path):
        self.domain_dir = domain_dir
        self.identity: dict = {}
        self.voice: dict = {}
        self.guardrails: dict = {}
        self.council: dict = {}
        self.manifest: dict = {}
        self._load()

    def _load(self) -> None:
        """Load all YAML files from the domain directory."""
        self.identity = self._read_yaml("identity.yaml")
        self.voice = self._read_yaml("voice.yaml")
        self.guardrails = self._read_yaml("guardrails.yaml")
        self.council = self._read_yaml("council.yaml")
        self.manifest = self._read_yaml("manifest.yaml")

    def _read_yaml(self, filename: str) -> dict:
        """Read a YAML file, returning empty dict if not found."""
        path = self.domain_dir / filename
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def build_system_prompt(self, uses: list[str] | None = None) -> str:
        """Build a system prompt from the domain context files.
        
        Args:
            uses: Which context files to include. None means all available.
                  Options: "identity", "voice", "guardrails"
        """
        parts = []

        if uses is None or "identity" in uses:
            if self.identity:
                parts.append(self._format_identity())

        if uses is None or "voice" in uses:
            if self.voice:
                parts.append(self._format_voice())

        if uses is None or "guardrails" in uses:
            if self.guardrails:
                parts.append(self._format_guardrails())

        return "\n\n".join(parts)

    def _format_identity(self) -> str:
        """Format identity.yaml into a system prompt section."""
        i = self.identity
        lines = ["## Identity & Context"]
        
        if i.get("name"):
            lines.append(f"You are writing as {i['name']}, {i.get('title', '')}.")
        if i.get("purpose"):
            lines.append(f"Purpose: {i['purpose']}")
        
        # Methodology
        method = i.get("methodology", {})
        if method:
            lines.append(f"\nMethodology: {method.get('name', '')}")
            for phase in method.get("phases", []):
                lines.append(f"  - {phase['name']}: {phase.get('description', '')}")

        # Positioning
        positioning = i.get("positioning", [])
        if positioning:
            lines.append("\nPositioning:")
            for p in positioning:
                lines.append(f"  - {p}")

        # Persistent context
        context = i.get("persistent_context", [])
        if context:
            lines.append("\nAlways remember:")
            for c in context:
                lines.append(f"  - {c}")

        return "\n".join(lines)

    def _format_voice(self) -> str:
        """Format voice.yaml into a system prompt section."""
        v = self.voice
        lines = ["## Voice & Style"]

        if v.get("tone"):
            lines.append(f"Tone: {v['tone']}")
        if v.get("perspective"):
            lines.append(f"Perspective: {v['perspective']}")

        # Rhythm rules
        rhythm = v.get("rhythm", [])
        if rhythm:
            lines.append("\nWriting rhythm:")
            for r in rhythm:
                lines.append(f"  - {r}")

        # Narrative preferences
        narrative = v.get("narrative", [])
        if narrative:
            lines.append("\nNarrative approach:")
            for n in narrative:
                lines.append(f"  - {n}")

        # Exemplars
        exemplars = v.get("exemplars", [])
        if exemplars:
            lines.append("\nExamples of good output:")
            for e in exemplars:
                lines.append(f'  "{e}"')

        return "\n".join(lines)

    def _format_guardrails(self) -> str:
        """Format guardrails.yaml into a system prompt section."""
        g = self.guardrails
        lines = ["## Quality Rules (MUST follow)"]

        banned = g.get("banned_words", [])
        if banned:
            lines.append(f"\nNEVER use these words: {', '.join(banned)}")

        patterns = g.get("banned_patterns", [])
        if patterns:
            lines.append("\nNEVER use these patterns:")
            for p in patterns:
                lines.append(f"  - {p}")

        checklist = g.get("pre_delivery_checklist", [])
        if checklist:
            lines.append("\nBefore outputting, verify:")
            for c in checklist:
                lines.append(f"  [ ] {c}")

        boundaries = g.get("boundaries", {})
        never = boundaries.get("never", [])
        always = boundaries.get("always", [])
        if never:
            lines.append("\nNever:")
            for n in never:
                lines.append(f"  - {n}")
        if always:
            lines.append("\nAlways:")
            for a in always:
                lines.append(f"  - {a}")

        return "\n".join(lines)

    def get_pipeline(self, name: str) -> dict:
        """Get a pipeline definition from the manifest."""
        pipelines = self.manifest.get("pipelines", {})
        if name not in pipelines:
            available = list(pipelines.keys())
            raise ValueError(
                f"Pipeline '{name}' not found. Available: {available}"
            )
        return pipelines[name]

    def get_constraints(self) -> dict:
        """Get execution constraints from the manifest."""
        return self.manifest.get("constraints", {})


class PromptExecutor:
    """Executes prompt-driven pipelines using domain YAML files.
    
    This is the core engine that turns YAML definitions into LLM calls.
    No Python code required from the user.
    """

    def __init__(self, domain_dir: Path, llm_client: Optional[BaseLLMClient] = None):
        self.domain_dir = Path(domain_dir)
        self.context = DomainContext(self.domain_dir)
        self._client = llm_client or self._create_default_client()

    def _create_default_client(self) -> BaseLLMClient:
        """Create LLM client from domain constraints or environment."""
        constraints = self.context.get_constraints()
        config = LLMConfig(
            provider=os.environ.get("KAZI_LLM_PROVIDER", "openai"),
            model=constraints.get("model", os.environ.get("KAZI_LLM_MODEL", "gpt-4o-mini")),
            temperature=constraints.get("temperature", 0.7),
            max_tokens=constraints.get("max_tokens_per_run", 4096),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        return create_llm_client(config)

    async def run(self, pipeline_name: str, input_data: dict) -> PipelineResult:
        """Run a named pipeline with the given input.
        
        Args:
            pipeline_name: Name of the pipeline from manifest.yaml
            input_data: User-provided input (e.g., {"topic": "..."})
            
        Returns:
            PipelineResult with the final output and stage details.
        """
        pipeline_def = self.context.get_pipeline(pipeline_name)
        stages = pipeline_def.get("stages", [])
        constraints = self.context.get_constraints()

        result = PipelineResult(
            pipeline=pipeline_name,
            status="running",
            model=constraints.get("model", "gpt-4o-mini"),
        )

        # Accumulate context between stages
        stage_outputs: list[StageResult] = []
        running_context = dict(input_data)

        for stage_def in stages:
            agent_name = stage_def.get("agent", "unknown")
            role = stage_def.get("role", "")
            goal = stage_def.get("goal", "")
            uses = stage_def.get("uses", None)
            output_type = stage_def.get("output", "text")

            logger.info(f"  Stage: {agent_name}")

            # Handle council review separately
            if agent_name == "council_review":
                stage_result = await self._run_council(running_context, stage_outputs)
            else:
                stage_result = await self._run_stage(
                    agent_name=agent_name,
                    role=role,
                    goal=goal,
                    uses=uses,
                    output_type=output_type,
                    running_context=running_context,
                    previous_outputs=stage_outputs,
                )

            stage_outputs.append(stage_result)
            result.stages.append(stage_result)
            result.total_tokens += stage_result.tokens_used

            # Update running context with this stage's output
            running_context[f"{agent_name}_output"] = stage_result.output

        # Final output is the last stage's output
        if stage_outputs:
            result.final_output = stage_outputs[-1].output

        # Guardrail check on final output
        if constraints.get("retry_on_guardrail_fail", False):
            passed = self._check_guardrails(result.final_output)
            if not passed:
                max_retries = constraints.get("max_retries", 2)
                for attempt in range(max_retries):
                    logger.info(f"  Guardrail retry {attempt + 1}/{max_retries}")
                    last_stage = stages[-1]
                    retry_result = await self._run_stage(
                        agent_name=last_stage.get("agent", "editor"),
                        role=last_stage.get("role", "Final editor"),
                        goal="Rewrite to pass all guardrail checks. Fix the violations.",
                        uses=last_stage.get("uses", ["voice", "guardrails"]),
                        output_type="text",
                        running_context=running_context,
                        previous_outputs=stage_outputs,
                    )
                    result.total_tokens += retry_result.tokens_used
                    if self._check_guardrails(retry_result.output):
                        result.final_output = retry_result.output
                        break
                else:
                    result.status = "guardrail_failed"
                    return result

        result.status = "completed"
        return result

    async def _run_stage(
        self,
        agent_name: str,
        role: str,
        goal: str,
        uses: list[str] | None,
        output_type: str,
        running_context: dict,
        previous_outputs: list[StageResult],
    ) -> StageResult:
        """Execute a single pipeline stage as an LLM call."""
        
        # Build system prompt from domain context
        system_prompt = self.context.build_system_prompt(uses)
        
        # Build the user prompt for this specific stage
        user_prompt = self._build_stage_prompt(
            role=role,
            goal=goal,
            running_context=running_context,
            previous_outputs=previous_outputs,
        )

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await self._client.complete(messages)

        return StageResult(
            agent=agent_name,
            output=response.content,
            tokens_used=response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0),
        )

    async def _run_council(
        self,
        running_context: dict,
        previous_outputs: list[StageResult],
    ) -> StageResult:
        """Run the advisory council on the current draft."""
        council = self.context.council
        if not council:
            return StageResult(agent="council_review", output="No council configured. Proceeding.")

        advisors = council.get("advisors", [])
        required_agreement = council.get("required_agreement", 3)

        # Get the latest draft from previous outputs
        latest_draft = previous_outputs[-1].output if previous_outputs else ""

        # Ask each advisor to evaluate
        evaluations = []
        total_tokens = 0

        for advisor in advisors:
            prompt = (
                f"You are {advisor['role']} ({advisor['id']}).\n"
                f"Your bias: {advisor['bias']}\n"
                f"Your key question: {advisor['question']}\n\n"
                f"Evaluate this draft:\n\n{latest_draft}\n\n"
                f"Respond with:\n"
                f"1. APPROVE or REVISE\n"
                f"2. One sentence explaining why\n"
                f"3. If REVISE, one specific suggestion"
            )

            messages = [
                LLMMessage(role="system", content="You are an advisory council member reviewing content."),
                LLMMessage(role="user", content=prompt),
            ]

            response = await self._client.complete(messages)
            evaluations.append({
                "advisor": advisor["id"],
                "feedback": response.content,
            })
            total_tokens += response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0)

        # Compile council feedback
        feedback_text = "\n\n".join(
            f"**{e['advisor']}**: {e['feedback']}" for e in evaluations
        )

        return StageResult(
            agent="council_review",
            output=feedback_text,
            tokens_used=total_tokens,
            council_feedback={"evaluations": evaluations},
        )

    def _build_stage_prompt(
        self,
        role: str,
        goal: str,
        running_context: dict,
        previous_outputs: list[StageResult],
    ) -> str:
        """Build the user-facing prompt for a pipeline stage."""
        parts = []

        parts.append(f"## Your Role\n{role}")
        parts.append(f"## Your Goal\n{goal}")

        # Include input data
        input_data = {k: v for k, v in running_context.items() if not k.endswith("_output")}
        if input_data:
            parts.append(f"## Input\n{json.dumps(input_data, indent=2)}")

        # Include relevant previous stage outputs
        if previous_outputs:
            parts.append("## Previous Stage Outputs")
            for stage in previous_outputs:
                parts.append(f"### {stage.agent}\n{stage.output}")

        return "\n\n".join(parts)

    def _check_guardrails(self, text: str) -> bool:
        """Check if text passes guardrail rules."""
        guardrails = self.context.guardrails
        if not guardrails:
            return True

        text_lower = text.lower()

        # Check banned words
        banned = guardrails.get("banned_words", [])
        for word in banned:
            if word.lower() in text_lower:
                logger.warning(f"  Guardrail violation: banned word '{word}'")
                return False

        return True

    async def dry_run(self, pipeline_name: str) -> dict:
        """Validate a pipeline without executing. Shows what would happen."""
        pipeline_def = self.context.get_pipeline(pipeline_name)
        stages = pipeline_def.get("stages", [])
        constraints = self.context.get_constraints()

        return {
            "pipeline": pipeline_name,
            "stages": [
                {
                    "agent": s.get("agent"),
                    "role": s.get("role"),
                    "goal": s.get("goal"),
                    "uses": s.get("uses"),
                }
                for s in stages
            ],
            "constraints": constraints,
            "domain_files_loaded": {
                "identity": bool(self.context.identity),
                "voice": bool(self.context.voice),
                "guardrails": bool(self.context.guardrails),
                "council": bool(self.context.council),
            },
        }
