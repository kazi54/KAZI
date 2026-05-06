"""ScoreLegend — configurable scoring tiers that map scores to actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScoreTier:
    """A tier in the scoring legend."""

    name: str
    min_score: float  # inclusive
    max_score: float  # exclusive (except last tier)
    action: str  # recommended action
    color: str = "#888888"  # display color (hex)
    description: str = ""

    def contains(self, score: float) -> bool:
        """Check if a score falls within this tier."""
        return self.min_score <= score < self.max_score


class ScoreLegend:
    """Configurable scoring system that maps numeric scores to actionable tiers.

    Each product defines its own legend. Examples:
        - CARTA: Abandon (0-40) → Evaluate (40-60) → Pursue (60-80) → Fast-track (80-100)
        - RFI: Dismiss (0-40) → Review (40-60) → Apply (60-80) → Strong Apply (80-100)

    Example:
        legend = ScoreLegend(tiers=[
            ScoreTier("Abandon", 0, 40, "abandon", "#ef4444"),
            ScoreTier("Evaluate", 40, 60, "evaluate", "#f59e0b"),
            ScoreTier("Pursue", 60, 80, "pursue", "#22c55e"),
            ScoreTier("Fast-track", 80, 101, "fast-track", "#10b981"),
        ])
        tier = legend.classify(75)  # → ScoreTier("Pursue", ...)
    """

    def __init__(self, tiers: list[ScoreTier]):
        # Sort by min_score ascending
        self.tiers = sorted(tiers, key=lambda t: t.min_score)

    def classify(self, score: float) -> ScoreTier:
        """Return the tier for a given score."""
        for tier in self.tiers:
            if tier.contains(score):
                return tier
        # If score exceeds all tiers, return the highest
        return self.tiers[-1]

    def to_dict(self) -> list[dict]:
        """Serialize legend for API/template use."""
        return [
            {
                "name": t.name,
                "min": t.min_score,
                "max": t.max_score,
                "action": t.action,
                "color": t.color,
                "description": t.description,
            }
            for t in self.tiers
        ]

    @classmethod
    def from_yaml(cls, data: list[dict]) -> ScoreLegend:
        """Create a ScoreLegend from YAML-parsed data."""
        tiers = [
            ScoreTier(
                name=d["name"],
                min_score=d["min"],
                max_score=d["max"],
                action=d.get("action", d["name"].lower()),
                color=d.get("color", "#888888"),
                description=d.get("description", ""),
            )
            for d in data
        ]
        return cls(tiers=tiers)

    def __repr__(self) -> str:
        tier_str = " | ".join(f"{t.name}({t.min_score}-{t.max_score})" for t in self.tiers)
        return f"ScoreLegend([{tier_str}])"
