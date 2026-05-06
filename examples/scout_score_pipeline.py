"""Scout → Score Pipeline — two-agent pipeline with scoring.

Demonstrates:
- BaseScoutAgent (data ingestion)
- BaseScoreAgent (multi-dimensional evaluation)
- Pipeline (sequential chain)
- ScoreLegend (tier classification)

Run:
    python examples/scout_score_pipeline.py
"""

import asyncio
from kazi.agents import BaseScoutAgent, BaseScoreAgent, AgentContext, AgentResult
from kazi.orchestrator import Pipeline
from kazi.scoring import ScoreLegend, ScoreTier


# --- Define Agents ---

class TopicScout(BaseScoutAgent):
    """Simulates discovering topics from external sources."""

    name = "topic-scout"

    async def crawl(self, query: dict, context: AgentContext) -> list[dict]:
        # In production, this would call an API or scrape a source
        return [
            {"title": "AI in Patent Law", "relevance": 85, "source": "arxiv"},
            {"title": "Machine Learning Basics", "relevance": 40, "source": "blog"},
            {"title": "Agent Orchestration Patterns", "relevance": 92, "source": "paper"},
        ]


class TopicScorer(BaseScoreAgent):
    """Scores topics based on relevance and quality."""

    name = "topic-scorer"

    async def score(self, entity: dict, context: AgentContext) -> dict[str, float]:
        # In production, this would use an LLM or heuristic scoring
        results = entity.get("results", [])
        if not results:
            return {"relevance": 0, "quality": 0}

        avg_relevance = sum(r.get("relevance", 50) for r in results) / len(results)
        quality = 70 if any(r["source"] == "paper" for r in results) else 50

        return {"relevance": avg_relevance, "quality": quality}


# --- Configure Scoring ---

legend = ScoreLegend(tiers=[
    ScoreTier("Skip", 0, 40, "skip", "#ef4444"),
    ScoreTier("Maybe", 40, 60, "review", "#f59e0b"),
    ScoreTier("Write", 60, 80, "write", "#22c55e"),
    ScoreTier("Priority", 80, 101, "priority", "#10b981"),
])


# --- Build Pipeline ---

pipeline = Pipeline(
    name="topic-discovery",
    stages=[TopicScout(), TopicScorer()],
)


async def main():
    context = AgentContext(job_id="demo-002", product="insight")

    print(f"Pipeline: {pipeline}")
    print()

    result = await pipeline.run({"domain": "AI + professional services"}, context)

    print(f"Success: {result.success}")
    print(f"Stages completed: {len(result.stage_results)}")
    print(f"Total duration: {result.total_duration_ms}ms")
    print()

    if result.success:
        overall = result.final_output.get("overall", 0)
        tier = legend.classify(overall)
        print(f"Overall score: {overall:.1f}")
        print(f"Tier: {tier.name} → Action: {tier.action}")
        print(f"Scores: {result.final_output.get('scores', {})}")


if __name__ == "__main__":
    asyncio.run(main())
