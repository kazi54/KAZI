"""Agent Registry — auto-discovers and indexes agent classes from domain plugins.

The registry is the lookup table that the PipelineBuilder uses to resolve
agent names (from manifest.yaml) to actual Python classes.

Discovery works by scanning a domain's `agents/` directory, importing all
modules, and finding subclasses of BaseAgent.

Usage:
    from kazi.agents.registry import AgentRegistry

    registry = AgentRegistry()
    registry.discover_domain("/path/to/domains/content")
    registry.discover_domain("/path/to/domains/ip-intel")

    # Now the PipelineBuilder can resolve agent names
    agent_cls = registry.get("content_scout")
    builder = PipelineBuilder(agent_registry=registry.agents)
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

from kazi.agents.base import BaseAgent


class AgentRegistry:
    """Central registry of all available agent classes.

    Agents are registered by their `name` class attribute. If two agents
    share a name, the later registration wins (with a warning).

    The registry supports:
    - Auto-discovery from domain `agents/` directories
    - Manual registration for testing or overrides
    - Namespace-aware lookup (domain.agent_name)
    """

    def __init__(self):
        self._agents: dict[str, type[BaseAgent]] = {}
        self._by_domain: dict[str, dict[str, type[BaseAgent]]] = {}

    @property
    def agents(self) -> dict[str, type[BaseAgent]]:
        """Flat dict of agent_name → agent_class. Used by PipelineBuilder."""
        return dict(self._agents)

    def register(
        self,
        agent_cls: type[BaseAgent],
        domain: str | None = None,
    ) -> None:
        """Manually register an agent class.

        Args:
            agent_cls: The agent class to register.
            domain: Optional domain namespace.
        """
        name = agent_cls.name
        if name in self._agents:
            existing = self._agents[name]
            print(
                f"  ⚠ Agent '{name}' already registered "
                f"({existing.__module__}), overwriting with {agent_cls.__module__}"
            )

        self._agents[name] = agent_cls

        if domain:
            if domain not in self._by_domain:
                self._by_domain[domain] = {}
            self._by_domain[domain][name] = agent_cls

    def get(self, name: str) -> type[BaseAgent] | None:
        """Get an agent class by name.

        Supports both flat names ("content_scout") and namespaced
        names ("content.content_scout").
        """
        # Try direct lookup first
        if name in self._agents:
            return self._agents[name]

        # Try namespaced lookup (domain.agent_name)
        if "." in name:
            domain, agent_name = name.split(".", 1)
            domain_agents = self._by_domain.get(domain, {})
            return domain_agents.get(agent_name)

        return None

    def get_domain_agents(self, domain: str) -> dict[str, type[BaseAgent]]:
        """Get all agents registered under a specific domain."""
        return dict(self._by_domain.get(domain, {}))

    def discover_domain(self, domain_path: str | Path) -> list[str]:
        """Auto-discover agent classes from a domain's agents/ directory.

        Scans all .py files in the agents/ subdirectory, imports them,
        and registers any BaseAgent subclasses found.

        Args:
            domain_path: Path to the domain directory (e.g., ./domains/content).

        Returns:
            List of agent names that were discovered and registered.
        """
        domain_path = Path(domain_path)
        agents_dir = domain_path / "agents"

        if not agents_dir.exists():
            return []

        domain_name = domain_path.name
        discovered: list[str] = []

        # Ensure the domain path is importable
        if str(domain_path.parent) not in sys.path:
            sys.path.insert(0, str(domain_path.parent))

        for py_file in sorted(agents_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            try:
                # Build a unique module name to avoid collisions
                module_name = f"domains.{domain_name}.agents.{py_file.stem}"

                # Load the module
                spec = importlib.util.spec_from_file_location(
                    module_name, py_file
                )
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Find all BaseAgent subclasses in the module
                for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(attr_value, BaseAgent)
                        and attr_value is not BaseAgent
                        and attr_value.__module__ == module_name
                    ):
                        self.register(attr_value, domain=domain_name)
                        discovered.append(attr_value.name)

            except Exception as e:
                print(f"  ⚠ Failed to import {py_file.name}: {e}")

        return discovered

    def discover_all_domains(self, domains_dir: str | Path) -> dict[str, list[str]]:
        """Discover agents from all domain directories.

        Args:
            domains_dir: Path to the top-level domains/ directory.

        Returns:
            Dict mapping domain_name → list of discovered agent names.
        """
        domains_path = Path(domains_dir)
        results: dict[str, list[str]] = {}

        if not domains_path.exists():
            return results

        for domain_path in sorted(domains_path.iterdir()):
            if not domain_path.is_dir() or domain_path.name.startswith("_"):
                continue

            discovered = self.discover_domain(domain_path)
            if discovered:
                results[domain_path.name] = discovered
                print(
                    f"  ✓ Discovered {len(discovered)} agents in "
                    f"'{domain_path.name}': {discovered}"
                )

        return results

    @property
    def count(self) -> int:
        """Total number of registered agents."""
        return len(self._agents)

    @property
    def domains(self) -> list[str]:
        """List of domains with registered agents."""
        return list(self._by_domain.keys())

    def __repr__(self) -> str:
        return (
            f"AgentRegistry(agents={self.count}, "
            f"domains={self.domains})"
        )

    def __contains__(self, name: str) -> bool:
        return name in self._agents
