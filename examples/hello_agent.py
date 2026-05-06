"""Hello Agent — your first KAZI agent in 10 lines.

Run:
    python examples/hello_agent.py
"""

import asyncio
from kazi.agents import BaseAgent, AgentContext, AgentResult


class HelloAgent(BaseAgent):
    """A minimal agent that greets the user."""

    name = "hello-agent"
    version = "0.1.0"

    async def execute(self, input: dict, context: AgentContext) -> AgentResult:
        name = input.get("name", "World")
        return AgentResult(
            success=True,
            data={"greeting": f"Hello, {name}! Welcome to KAZI."},
        )


async def main():
    agent = HelloAgent()
    context = AgentContext(job_id="demo-001")

    result = await agent.run({"name": "Dr. Jean"}, context)

    print(f"Success: {result.success}")
    print(f"Output: {result.data}")
    print(f"Duration: {result.duration_ms}ms")


if __name__ == "__main__":
    asyncio.run(main())
