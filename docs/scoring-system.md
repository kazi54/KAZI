# Scoring System

The scoring system is KAZI OS's evaluation engine. It provides a configurable, multi-dimensional framework for assessing any kind of item — market signals, competitor moves, content topics, candidates — against domain-specific rubrics.

---

## Concepts

The scoring system has three layers:

| Layer | What it defines | Configured in |
|-------|----------------|---------------|
| **Dimensions** | The axes of evaluation (what you measure) | `scoring.yaml` |
| **Weights** | Relative importance of each dimension | `scoring.yaml` |
| **Legend** | How numeric scores map to actionable tiers | `scoring.yaml` |

Together, these produce a **composite score** (0-100) and a **tier classification** (e.g., "Abandon", "Pursue") for every evaluated item.

---

## Configuration

Every domain defines its scoring system in `scoring.yaml`:

```yaml
# domains/my-domain/scoring.yaml

dimensions:
  - name: market_size
    weight: 0.25
    description: "Total addressable market for this technology"
    scoring_guide: |
      0-20: Niche market (<$100M TAM)
      20-40: Small market ($100M-$500M TAM)
      40-60: Medium market ($500M-$2B TAM)
      60-80: Large market ($2B-$10B TAM)
      80-100: Massive market (>$10B TAM)

  - name: competitive_advantage
    weight: 0.25
    description: "Strength of IP protection and differentiation"
    scoring_guide: |
      0-20: No meaningful protection, easily replicated
      20-40: Weak protection, several alternatives exist
      40-60: Moderate protection, some differentiation
      60-80: Strong protection, clear moat
      80-100: Exceptional protection, no viable alternatives

  - name: implementation_readiness
    weight: 0.20
    description: "How close is this to being deployable/licensable?"
    scoring_guide: |
      0-20: Theoretical concept only
      20-40: Lab-proven, far from production
      40-60: Prototype exists, needs development
      60-80: Near-production, clear path to deployment
      80-100: Production-ready, immediate deployment possible

  - name: urgency
    weight: 0.15
    description: "Time-sensitivity of the signal — how soon must we act?"
    scoring_guide: |
      0-20: No time pressure, background trend
      20-40: Low urgency, worth noting for next quarter
      40-60: Moderate urgency, address within 2-4 weeks
      60-80: High urgency, competitive window closing
      80-100: Critical — immediate action required

  - name: strategic_alignment
    weight: 0.15
    description: "Fit with the institution's strategic priorities"
    scoring_guide: |
      0-20: Misaligned with institutional goals
      20-40: Tangential relevance
      40-60: Moderate alignment
      60-80: Strong alignment with stated priorities
      80-100: Core to institutional mission

legend:
  - range: [0, 40]
    tier: abandon
    label: "Abandon"
    color: "#ef4444"
    action: "Do not pursue. Release or let lapse."
  - range: [40, 60]
    tier: evaluate
    label: "Evaluate"
    color: "#f59e0b"
    action: "Needs further analysis before committing resources."
  - range: [60, 80]
    tier: pursue
    label: "Pursue"
    color: "#22c55e"
    action: "Proceed with commercialization. Allocate resources."
  - range: [80, 100]
    tier: fast_track
    label: "Fast-track"
    color: "#06b6d4"
    action: "Immediate priority. Accelerate timeline."
```

---

## How Scoring Works

### Step 1: Dimension Scoring

Each dimension receives a score from 0 to 100. This score can come from:

- **An LLM agent** — the agent evaluates the item against the `scoring_guide` and assigns a numeric score
- **A deterministic function** — computed from data (e.g., citation count → score via a lookup table)
- **A hybrid** — LLM proposes, deterministic function validates/adjusts

### Step 2: Weighted Composite

The overall score is the weighted sum of all dimension scores:

```
overall = Σ (dimension_score × dimension_weight)
```

For the example above:
```
overall = (market × 0.25) + (competitive × 0.25) + (readiness × 0.20) 
        + (urgency × 0.15) + (strategic × 0.15)
```

All weights must sum to 1.0. The platform validates this at startup.

### Step 3: Tier Classification

The overall score is mapped to a tier using the legend:

```
0-40   → Abandon (red)
40-60  → Evaluate (amber)
60-80  → Pursue (green)
80-100 → Fast-track (cyan)
```

---

## Using the Scoring System in Agents

Score agents access the domain's scoring configuration via `self.scoring_system`:

```python
from kazi.agents import BaseScoreAgent

class MyScoreAgent(BaseScoreAgent):
    name = "my_scorer"
    description = "Scores items against the domain rubric"

    async def run(self, input_data: dict) -> dict:
        item = input_data["_context"]["scout"]
        
        # Score each dimension
        dimension_scores = {}
        for dim in self.scoring_system.dimensions:
            score = await self.evaluate_dimension(item, dim)
            dimension_scores[dim.name] = score
        
        # Compute weighted overall
        overall = self.scoring_system.compute(dimension_scores)
        
        # Classify into tier
        tier = self.scoring_system.legend.classify(overall)
        
        return {
            "dimensions": dimension_scores,
            "overall_score": overall,
            "tier": tier.name,
            "tier_label": tier.label,
            "tier_color": tier.color,
            "recommendation": tier.action,
        }
    
    async def evaluate_dimension(self, item: dict, dimension) -> float:
        """Use LLM to score one dimension."""
        prompt = f"""
        Evaluate this item against the following dimension:
        
        Dimension: {dimension.name}
        Description: {dimension.description}
        
        Scoring Guide:
        {dimension.scoring_guide}
        
        Item data:
        {item}
        
        Return a score from 0 to 100.
        """
        response = await self.tools.llm.complete(prompt=prompt, temperature=0.1)
        return float(response)
```

---

## The ScoreLegend API

```python
from kazi.scoring import ScoreLegend, ScoreTier

# Load from scoring.yaml (automatic in domain context)
legend = ScoreLegend.from_yaml("scoring.yaml")

# Classify a score
tier = legend.classify(72)
# tier.name = "pursue"
# tier.label = "Pursue"
# tier.color = "#22c55e"
# tier.action = "Proceed with commercialization. Allocate resources."

# Get all tiers
for tier in legend.tiers:
    print(f"{tier.range}: {tier.label} ({tier.color})")

# Check if score meets a threshold
if legend.classify(score).name in ["pursue", "fast_track"]:
    # Proceed with delivery
    ...
```

---

## The ScoringSystem API

```python
from kazi.scoring import ScoringSystem

# Load from scoring.yaml
system = ScoringSystem.from_yaml("scoring.yaml")

# Compute weighted score
dimension_scores = {
    "market_size": 75,
    "competitive_advantage": 60,
    "implementation_readiness": 80,
    "urgency": 55,
    "strategic_alignment": 70,
}

overall = system.compute(dimension_scores)
# overall = (75×0.25) + (60×0.25) + (80×0.20) + (55×0.15) + (70×0.15)
# overall = 18.75 + 15.0 + 16.0 + 8.25 + 10.5 = 68.5

tier = system.legend.classify(overall)
# tier.name = "pursue"
```

---

## Customizing the Legend

The default legend uses four tiers, but you can define any number:

```yaml
# Three-tier example (simpler)
legend:
  - range: [0, 33]
    tier: no
    label: "No"
    color: "#ef4444"
    action: "Reject"
  - range: [33, 66]
    tier: maybe
    label: "Maybe"
    color: "#f59e0b"
    action: "Investigate further"
  - range: [66, 100]
    tier: yes
    label: "Yes"
    color: "#22c55e"
    action: "Accept"
```

```yaml
# Five-tier example (more granular)
legend:
  - range: [0, 20]
    tier: dismiss
    label: "Dismiss"
    color: "#ef4444"
    action: "Not relevant"
  - range: [20, 40]
    tier: low_fit
    label: "Low Fit"
    color: "#f97316"
    action: "Unlikely match"
  - range: [40, 60]
    tier: review
    label: "Review"
    color: "#f59e0b"
    action: "Warrants closer look"
  - range: [60, 80]
    tier: apply
    label: "Apply"
    color: "#22c55e"
    action: "Strong candidate"
  - range: [80, 100]
    tier: strong_apply
    label: "Strong Apply"
    color: "#06b6d4"
    action: "Top priority — act immediately"
```

---

## Score Visualization

The scoring system integrates with the template renderer to produce visual score representations in reports:

| Visualization | Use case |
|---------------|----------|
| Colored dot | Inline tier indicator (e.g., in tables) |
| Score ring | Circular progress showing overall score |
| Dimension bar chart | Horizontal bars showing each dimension |
| Radar chart | Multi-dimensional comparison |
| Score grid | 5-score summary with colored backgrounds |

Templates access scores via Jinja2 variables:

```html
<!-- Score dot -->
<span class="score-dot" style="background: {{tier_color}}"></span>
{{tier_label}} ({{overall_score}}/100)

<!-- Dimension bars -->
{% for dim_name, dim_score in dimensions.items() %}
<div class="dimension-bar">
  <span class="dim-label">{{dim_name}}</span>
  <div class="bar" style="width: {{dim_score}}%; background: {{legend.classify(dim_score).color}}"></div>
  <span class="dim-score">{{dim_score}}</span>
</div>
{% endfor %}
```

---

## Score History and Drift Detection

The platform stores every score computation in the `ScoreStore`. This enables:

1. **Historical tracking** — see how an item's score changes over time
2. **Drift detection** — alert when a score changes significantly from baseline
3. **Confidence decay** — reduce confidence in older scores automatically

```python
# Check for drift
from kazi.scoring import DriftDetector

detector = DriftDetector(threshold=15)  # Alert if score changes by >15 points

current_score = 72
historical_score = await score_store.get_latest(item_id="signal_ev_2024_q3")

if detector.has_drifted(current_score, historical_score):
    # Trigger re-evaluation or alert
    await alert_dispatcher.notify(
        message=f"Score drifted: {historical_score} → {current_score}",
        item_id="signal_ev_2024_q3",
    )
```

---

## Design Guidelines

When designing scoring rubrics for a new domain:

1. **Start with 3-5 dimensions.** More than 7 dilutes the signal. Each dimension should be independently measurable.

2. **Make scoring guides concrete.** Avoid vague language like "good" or "strong." Use observable criteria: numbers, thresholds, presence/absence of specific attributes.

3. **Weight by decision impact.** The dimension that most changes the recommended action should have the highest weight.

4. **Test with edge cases.** Score 5-10 items manually before deploying. Verify the legend produces sensible tier assignments.

5. **Iterate based on HITL feedback.** If human reviewers consistently override a dimension's score, the scoring guide needs refinement.
