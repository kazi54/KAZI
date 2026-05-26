"""KAZI OS — Domain-agnostic platform for AI-powered professional services."""

__version__ = "0.3.0"

# ── Agents ────────────────────────────────────────────────────────────────────
from kazi.agents.base import BaseAgent
from kazi.agents.registry import AgentRegistry

# ── Orchestration ─────────────────────────────────────────────────────────────
from kazi.orchestrator.pipeline import Pipeline
from kazi.orchestrator.fanout import FanOut
from kazi.orchestrator.orchestrator import Orchestrator
from kazi.orchestrator.builder import PipelineBuilder

# ── Scoring ───────────────────────────────────────────────────────────────────
from kazi.scoring.legend import ScoreLegend
from kazi.scoring.dimensions import ScoringDimension

# ── Delivery ──────────────────────────────────────────────────────────────────
from kazi.delivery.destinations import (
    BaseDestination,
    DestinationRegistry,
    DestinationReceipt,
)
from kazi.delivery.renderer import TemplateRenderer

# ── Platform ──────────────────────────────────────────────────────────────────
from kazi.platform.tenant import TenantConfig, load_tenant, load_all_tenants

# ── Human-in-the-Loop ─────────────────────────────────────────────────────────
from kazi.hitl.processor import HITLProcessor, Resolution

# ── State ─────────────────────────────────────────────────────────────────────
from kazi.state.store import StateBackend, create_state_store

# ── Utilities ─────────────────────────────────────────────────────────────────
from kazi.utils.llm import (
    BaseLLMClient,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    create_llm_client,
    create_llm_client_from_env,
)
from kazi.utils.retry import RetryConfig, retry_async, with_retry, CircuitBreaker
from kazi.utils.validation import (
    SchemaValidator,
    FieldSpec,
    ValidationResult,
    validate_and_repair,
)

__all__ = [
    # Agents
    "BaseAgent",
    "AgentRegistry",
    # Orchestration
    "Pipeline",
    "FanOut",
    "Orchestrator",
    "PipelineBuilder",
    # Scoring
    "ScoreLegend",
    "ScoringDimension",
    # Delivery
    "BaseDestination",
    "DestinationRegistry",
    "DestinationReceipt",
    "TemplateRenderer",
    # Platform
    "TenantConfig",
    "load_tenant",
    "load_all_tenants",
    # HITL
    "HITLProcessor",
    "Resolution",
    # State
    "StateBackend",
    "create_state_store",
    # Utils — LLM
    "BaseLLMClient",
    "LLMConfig",
    "LLMMessage",
    "LLMResponse",
    "create_llm_client",
    "create_llm_client_from_env",
    # Utils — Retry
    "RetryConfig",
    "retry_async",
    "with_retry",
    "CircuitBreaker",
    # Utils — Validation
    "SchemaValidator",
    "FieldSpec",
    "ValidationResult",
    "validate_and_repair",
]
