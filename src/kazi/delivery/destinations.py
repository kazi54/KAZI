"""Destinations — the abstraction layer between KAZI OS and external systems.

KAZI OS does not know what a CRM is. It knows what a Destination is.
A destination is anywhere pipeline output gets pushed: Notion, Salesforce,
Airtable, email, webhook, or anything else.

Tenants declare which destinations they use in their tenant config.
KAZI OS routes to them via adapters.

Usage:
    from kazi.delivery.destinations import DestinationRegistry

    registry = DestinationRegistry()
    registry.register("notion", NotionDestination)
    registry.register("webhook", WebhookDestination)

    # Resolve from tenant config
    dest = registry.resolve("review", tenant_config)
    receipt = await dest.push(payload, context)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kazi.agents.base import AgentContext


# ═══════════════════════════════════════════════════════════════════════════════
# Core Abstractions
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DestinationReceipt:
    """Proof that a payload was successfully pushed to a destination.

    Attributes:
        destination_name: Which adapter handled this (e.g., "notion", "webhook").
        external_id: The ID in the external system (e.g., Notion page ID, SF record ID).
        url: Direct link to the item in the external system (if available).
        timestamp: When the push was completed.
        metadata: Any adapter-specific metadata.
    """

    destination_name: str
    external_id: str
    url: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DestinationStatus:
    """Status of a previously pushed item.

    Used by HITL to check if a human has reviewed/approved something.

    Attributes:
        external_id: The ID from the original receipt.
        status: Current status string (adapter-specific, but normalized).
        resolved: Whether the item has been actioned (approved/rejected/etc).
        resolved_by: Who resolved it (if known).
        resolved_at: When it was resolved (if known).
    """

    external_id: str
    status: str  # "pending" | "approved" | "rejected" | "expired"
    resolved: bool = False
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDestination(ABC):
    """Abstract base for all destination adapters.

    Every destination must implement:
    - push(): Send a payload to the external system
    - check_status(): Check if a previously pushed item has been actioned

    Optionally:
    - validate_config(): Verify that the adapter's config is valid
    - health_check(): Test connectivity to the external system
    """

    name: str = "base"

    @abstractmethod
    async def push(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        config: dict[str, Any],
    ) -> DestinationReceipt:
        """Push a deliverable to this destination.

        Args:
            payload: The data to push (pipeline output, report, notification).
            context: Execution context (contains org_id, job_id, etc.).
            config: Adapter-specific configuration from tenant.yaml.

        Returns:
            A receipt proving the push succeeded.
        """
        raise NotImplementedError

    @abstractmethod
    async def check_status(
        self,
        external_id: str,
        config: dict[str, Any],
    ) -> DestinationStatus:
        """Check the status of a previously pushed item.

        Used by the HITL system to determine if a human has reviewed
        and approved (or rejected) a deliverable.

        Args:
            external_id: The ID from the original DestinationReceipt.
            config: Adapter-specific configuration from tenant.yaml.

        Returns:
            Current status of the item.
        """
        raise NotImplementedError

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        """Validate adapter configuration. Returns list of errors (empty = valid).

        Override to add adapter-specific validation.
        """
        return []

    async def health_check(self, config: dict[str, Any]) -> bool:
        """Test connectivity to the external system. Returns True if healthy.

        Override to add adapter-specific health checks.
        """
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# Built-in Adapters
# ═══════════════════════════════════════════════════════════════════════════════


class NotionDestination(BaseDestination):
    """Push deliverables to a Notion workspace.

    Config expected:
        workspace_id: str
        database_id: str (for database items) OR parent_page_id: str (for pages)
        token: str (integration token)
    """

    name = "notion"

    async def push(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        config: dict[str, Any],
    ) -> DestinationReceipt:
        """Create or update a page/database item in Notion."""
        # Import here to avoid hard dependency
        from httpx import AsyncClient

        token = config["token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        # Determine target: database item or child page
        database_id = config.get("database_id")
        parent_page_id = config.get("parent_page_id")

        async with AsyncClient() as client:
            if database_id:
                # Create database item
                body = {
                    "parent": {"database_id": database_id},
                    "properties": payload.get("properties", {}),
                }
                if "children" in payload:
                    body["children"] = payload["children"]

                resp = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=body,
                )
            else:
                # Create child page
                body = {
                    "parent": {"page_id": parent_page_id},
                    "properties": {
                        "title": {
                            "title": [
                                {"text": {"content": payload.get("title", "Untitled")}}
                            ]
                        }
                    },
                }
                if "children" in payload:
                    body["children"] = payload["children"]

                resp = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=body,
                )

            resp.raise_for_status()
            data = resp.json()

            return DestinationReceipt(
                destination_name=self.name,
                external_id=data["id"],
                url=data.get("url"),
                metadata={"object": data.get("object"), "parent": data.get("parent")},
            )

    async def check_status(
        self,
        external_id: str,
        config: dict[str, Any],
    ) -> DestinationStatus:
        """Check a Notion page's status property for review state."""
        from httpx import AsyncClient

        token = config["token"]
        status_property = config.get("status_property", "Status")

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        }

        async with AsyncClient() as client:
            resp = await client.get(
                f"https://api.notion.com/v1/pages/{external_id}",
                headers=headers,
            )
            resp.raise_for_status()
            page = resp.json()

        # Extract status from properties
        props = page.get("properties", {})
        status_prop = props.get(status_property, {})

        # Handle different property types
        status_value = "pending"
        if status_prop.get("type") == "status":
            status_value = status_prop.get("status", {}).get("name", "pending")
        elif status_prop.get("type") == "select":
            status_value = status_prop.get("select", {}).get("name", "pending")

        # Normalize to our status vocabulary
        resolved = status_value.lower() in ("approved", "done", "complete", "rejected")

        return DestinationStatus(
            external_id=external_id,
            status=status_value.lower(),
            resolved=resolved,
        )

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("token"):
            errors.append("Notion adapter requires 'token' in config")
        if not config.get("database_id") and not config.get("parent_page_id"):
            errors.append(
                "Notion adapter requires either 'database_id' or 'parent_page_id'"
            )
        return errors


class WebhookDestination(BaseDestination):
    """Push deliverables via HTTP POST to any endpoint.

    Config expected:
        url: str (the webhook URL)
        headers: dict (optional additional headers)
        method: str (optional, defaults to POST)
    """

    name = "webhook"

    async def push(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        config: dict[str, Any],
    ) -> DestinationReceipt:
        """POST payload to the configured webhook URL."""
        from httpx import AsyncClient

        url = config["url"]
        headers = config.get("headers", {})
        method = config.get("method", "POST").upper()

        # Enrich payload with context
        body = {
            "payload": payload,
            "context": {
                "job_id": context.job_id,
                "org_id": context.org_id,
                "product": context.product,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        async with AsyncClient() as client:
            resp = await client.request(method, url, json=body, headers=headers)
            resp.raise_for_status()

        return DestinationReceipt(
            destination_name=self.name,
            external_id=f"webhook-{context.job_id}",
            url=url,
            metadata={"status_code": resp.status_code},
        )

    async def check_status(
        self,
        external_id: str,
        config: dict[str, Any],
    ) -> DestinationStatus:
        """Webhooks are fire-and-forget. Status is always 'delivered'."""
        return DestinationStatus(
            external_id=external_id,
            status="delivered",
            resolved=True,
        )

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("url"):
            errors.append("Webhook adapter requires 'url' in config")
        return errors


class EmailDestination(BaseDestination):
    """Push deliverables via email.

    Config expected:
        to: str | list[str] (recipient addresses)
        from_address: str (sender address)
        smtp_host: str
        smtp_port: int
        smtp_user: str
        smtp_password: str
        subject_template: str (optional, Jinja2 template)
    """

    name = "email"

    async def push(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        config: dict[str, Any],
    ) -> DestinationReceipt:
        """Send payload as email. Implementation deferred to product layer."""
        # Minimal implementation — product layer should override with
        # proper SMTP/SES/SendGrid integration
        import uuid

        receipt_id = str(uuid.uuid4())

        # In production, this would:
        # 1. Render the payload through a template
        # 2. Send via SMTP/API
        # 3. Return the message ID

        return DestinationReceipt(
            destination_name=self.name,
            external_id=receipt_id,
            metadata={
                "to": config.get("to"),
                "subject": payload.get("subject", "KAZI Delivery"),
                "status": "queued",
            },
        )

    async def check_status(
        self,
        external_id: str,
        config: dict[str, Any],
    ) -> DestinationStatus:
        """Email status tracking requires external service (SendGrid, etc)."""
        return DestinationStatus(
            external_id=external_id,
            status="sent",
            resolved=True,
        )

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = []
        if not config.get("to"):
            errors.append("Email adapter requires 'to' in config")
        return errors


# ═══════════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════════


class DestinationRegistry:
    """Registry of available destination adapters.

    Products register adapters at startup. Tenant configs reference them by name.

    Example:
        registry = DestinationRegistry()
        # Built-ins are auto-registered

        # Resolve for a specific tenant destination key
        dest = registry.resolve("review", tenant_destinations_config)
        receipt = await dest.push(payload, context, dest_config)
    """

    def __init__(self):
        self._adapters: dict[str, type[BaseDestination]] = {}
        # Auto-register built-in adapters
        self.register("notion", NotionDestination)
        self.register("webhook", WebhookDestination)
        self.register("email", EmailDestination)

    def register(self, name: str, adapter_cls: type[BaseDestination]) -> None:
        """Register a destination adapter by name."""
        self._adapters[name] = adapter_cls

    def get_adapter(self, adapter_name: str) -> BaseDestination:
        """Get an adapter instance by name.

        Args:
            adapter_name: The adapter type (e.g., "notion", "webhook").

        Returns:
            An instance of the adapter.

        Raises:
            ValueError: If the adapter is not registered.
        """
        cls = self._adapters.get(adapter_name)
        if cls is None:
            raise ValueError(
                f"Destination adapter '{adapter_name}' not registered. "
                f"Available: {list(self._adapters.keys())}"
            )
        return cls()

    def resolve(
        self,
        destination_key: str,
        tenant_destinations: dict[str, dict[str, Any]],
    ) -> tuple[BaseDestination, dict[str, Any]]:
        """Resolve a destination key from tenant config to an adapter + config.

        Args:
            destination_key: The logical name (e.g., "review", "publish", "notify").
            tenant_destinations: The tenant's `destinations:` config block.

        Returns:
            Tuple of (adapter_instance, adapter_config).

        Raises:
            ValueError: If the destination key is not in tenant config.
            ValueError: If the adapter type is not registered.
        """
        dest_config = tenant_destinations.get(destination_key)
        if dest_config is None:
            raise ValueError(
                f"Destination '{destination_key}' not found in tenant config. "
                f"Available: {list(tenant_destinations.keys())}"
            )

        adapter_name = dest_config.get("adapter")
        if not adapter_name:
            raise ValueError(
                f"Destination '{destination_key}' missing 'adapter' field"
            )

        adapter = self.get_adapter(adapter_name)
        config = dest_config.get("config", {})

        return adapter, config

    @property
    def available_adapters(self) -> list[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())

    def __repr__(self) -> str:
        return f"DestinationRegistry(adapters={self.available_adapters})"
