"""ScoringDimension — weighted multi-factor scoring."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoringDimension:
    """A single dimension in a multi-factor scoring system.

    Example:
        market_dim = ScoringDimension(
            name="market_potential",
            weight=0.30,
            description="Addressable market size and growth trajectory",
            sub_factors=["tam_size", "growth_rate", "competitive_density"]
        )
    """

    name: str
    weight: float  # 0.0 to 1.0, all dimensions should sum to 1.0
    description: str = ""
    sub_factors: list[str] = field(default_factory=list)

    def weighted_score(self, raw_score: float) -> float:
        """Apply weight to a raw score (0-100)."""
        return raw_score * self.weight


class ScoringSystem:
    """Multi-dimensional scoring system with configurable dimensions.

    Example:
        system = ScoringSystem(dimensions=[
            ScoringDimension("market", 0.30, "Market potential"),
            ScoringDimension("legal", 0.25, "Legal strength"),
            ScoringDimension("technical", 0.20, "Technical merit"),
            ScoringDimension("commercial", 0.15, "Commercial readiness"),
            ScoringDimension("strategic", 0.10, "Strategic alignment"),
        ])
        overall = system.compute_overall({"market": 80, "legal": 65, ...})
    """

    def __init__(self, dimensions: list[ScoringDimension]):
        self.dimensions = dimensions
        self._validate_weights()

    def _validate_weights(self) -> None:
        """Ensure weights sum to approximately 1.0."""
        total = sum(d.weight for d in self.dimensions)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Dimension weights must sum to 1.0, got {total:.2f}. "
                f"Dimensions: {[d.name for d in self.dimensions]}"
            )

    def compute_overall(self, scores: dict[str, float]) -> float:
        """Compute weighted overall score from dimension scores.

        Args:
            scores: Mapping of dimension_name → raw_score (0-100)

        Returns:
            Weighted overall score (0-100)
        """
        overall = 0.0
        for dim in self.dimensions:
            raw = scores.get(dim.name, 0)
            overall += dim.weighted_score(raw)
        return round(overall, 1)

    def get_dimension(self, name: str) -> ScoringDimension | None:
        """Get a dimension by name."""
        for dim in self.dimensions:
            if dim.name == name:
                return dim
        return None

    @classmethod
    def from_yaml(cls, data: dict) -> ScoringSystem:
        """Create a ScoringSystem from YAML-parsed data.

        Expected format:
            dimensions:
              - name: market
                weight: 0.30
                description: Market potential
                sub_factors: [tam_size, growth_rate]
        """
        dimensions = [
            ScoringDimension(
                name=d["name"],
                weight=d["weight"],
                description=d.get("description", ""),
                sub_factors=d.get("sub_factors", []),
            )
            for d in data.get("dimensions", [])
        ]
        return cls(dimensions=dimensions)

    def __repr__(self) -> str:
        dims = ", ".join(f"{d.name}({d.weight:.0%})" for d in self.dimensions)
        return f"ScoringSystem([{dims}])"
