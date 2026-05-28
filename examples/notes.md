# Example Domain Design Notes

## Hypothetical Thought Leader: "Marcus Chen"
- Leadership coach specializing in executive transitions
- Publishes weekly LinkedIn posts + monthly deep-dive articles
- Has a methodology: "The Transition Framework" (5 phases)
- Wants to scale content production without losing his voice

## Domain Files (inspired by Jan's 12-file architecture):
1. identity.yaml — who Marcus is, his methodology, positioning
2. voice.yaml — his writing style rules
3. guardrails.yaml — banned words, patterns, quality checklist
4. council.yaml — advisory perspectives for content decisions
5. manifest.yaml — pipelines (weekly post, monthly article)
6. templates/ — output formats

## The Test Flow:
1. pip install (from repo)
2. kazi init marcus-chen
3. Fill in the YAML files (we provide the example)
4. kazi run weekly-post --input '{"topic": "Why most leadership transitions fail in the first 90 days"}'
5. See structured output (LinkedIn post draft)
