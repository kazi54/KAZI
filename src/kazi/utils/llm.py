"""
LLM Client — Domain-agnostic language model abstraction.

Provides a unified interface for calling LLMs regardless of provider.
Agents use this instead of importing openai/anthropic directly.

Supported providers:
  - OpenAI (GPT-4, GPT-4o, GPT-3.5)
  - Anthropic (Claude 3.5, Claude 3)
  - Any OpenAI-compatible API (Groq, Together, local models)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """A single message in a conversation."""
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    usage: dict = field(default_factory=dict)  # {"prompt_tokens": n, "completion_tokens": n}
    raw: Optional[Any] = None  # Provider-specific raw response


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""
    provider: str = "openai"  # "openai" | "anthropic" | "openai_compatible"
    model: str = "gpt-4o"
    api_key: Optional[str] = None  # Falls back to env var
    base_url: Optional[str] = None  # For OpenAI-compatible providers
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120


class BaseLLMClient(ABC):
    """Abstract LLM client interface."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a completion request to the LLM."""
        ...

    @abstractmethod
    async def complete_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: Optional[float] = None,
    ) -> dict:
        """Send a completion request expecting structured JSON output matching schema."""
        ...


class OpenAIClient(BaseLLMClient):
    """OpenAI and OpenAI-compatible API client."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")

        api_key = config.api_key or os.environ.get("OPENAI_API_KEY")
        kwargs = {"api_key": api_key, "timeout": config.timeout}
        if config.base_url:
            kwargs["base_url"] = config.base_url

        self._client = AsyncOpenAI(**kwargs)

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            raw=response,
        )

    async def complete_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: Optional[float] = None,
    ) -> dict:
        # Append schema instruction to system message
        schema_instruction = (
            f"\nYou MUST respond with valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```"
        )
        augmented = list(messages)
        if augmented and augmented[0].role == "system":
            augmented[0] = LLMMessage(
                role="system",
                content=augmented[0].content + schema_instruction,
            )
        else:
            augmented.insert(0, LLMMessage(role="system", content=schema_instruction))

        response = await self.complete(augmented, temperature=temperature, json_mode=True)
        return json.loads(response.content)


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package required. Install with: pip install anthropic")

        api_key = config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = AsyncAnthropic(api_key=api_key, timeout=config.timeout)

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        # Anthropic separates system from messages
        system_msg = ""
        user_messages = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            else:
                user_messages.append({"role": m.role, "content": m.content})

        if json_mode:
            system_msg += "\nRespond with valid JSON only. No markdown, no explanation."

        kwargs = {
            "model": self.config.model,
            "messages": user_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
        }
        if system_msg.strip():
            kwargs["system"] = system_msg.strip()

        response = await self._client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text if response.content else "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
            },
            raw=response,
        )

    async def complete_structured(
        self,
        messages: list[LLMMessage],
        schema: dict,
        temperature: Optional[float] = None,
    ) -> dict:
        schema_instruction = (
            f"\nRespond with valid JSON matching this schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```"
        )
        augmented = list(messages)
        if augmented and augmented[0].role == "system":
            augmented[0] = LLMMessage(
                role="system",
                content=augmented[0].content + schema_instruction,
            )
        else:
            augmented.insert(0, LLMMessage(role="system", content=schema_instruction))

        response = await self.complete(augmented, temperature=temperature, json_mode=True)
        return json.loads(response.content)


# ─── Factory ──────────────────────────────────────────────────────────────────


_PROVIDERS = {
    "openai": OpenAIClient,
    "openai_compatible": OpenAIClient,
    "anthropic": AnthropicClient,
}


def create_llm_client(config: LLMConfig) -> BaseLLMClient:
    """
    Factory for creating LLM clients.

    Usage:
        config = LLMConfig(provider="openai", model="gpt-4o")
        client = create_llm_client(config)
        response = await client.complete([LLMMessage("user", "Hello")])
    """
    provider = config.provider.lower()
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Available: {', '.join(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider](config)


def create_llm_client_from_env(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMClient:
    """
    Create an LLM client from environment variables.

    Checks for:
      KAZI_LLM_PROVIDER (default: "openai")
      KAZI_LLM_MODEL (default: "gpt-4o")
      KAZI_LLM_BASE_URL (optional, for compatible APIs)
      OPENAI_API_KEY or ANTHROPIC_API_KEY
    """
    config = LLMConfig(
        provider=provider or os.environ.get("KAZI_LLM_PROVIDER", "openai"),
        model=model or os.environ.get("KAZI_LLM_MODEL", "gpt-4o"),
        base_url=os.environ.get("KAZI_LLM_BASE_URL"),
    )
    return create_llm_client(config)
