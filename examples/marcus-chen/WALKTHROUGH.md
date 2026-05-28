# KAZI OS Walkthrough: Building a Content System for a Thought Leader

This walkthrough takes you from zero to a working AI content pipeline in under 10 minutes. You will build a system that produces LinkedIn posts and newsletter articles in a specific voice, reviewed by an advisory council, and validated against quality guardrails.

No Python required. The entire system is defined in YAML files.

---

## The Scenario

**Marcus Chen** is a fictional executive transition coach. He helps newly appointed leaders navigate their first 90 days. He wants an AI system that:

1. Researches a topic he provides
2. Writes a LinkedIn post in his voice
3. Runs the draft through a 5-person advisory council
4. Edits based on feedback and delivers a publication-ready post

His system is defined in 5 files. No code.

---

## Step 1: Install KAZI OS

```bash
git clone https://github.com/kazi54/KAZI.git
cd KAZI
pip install -e .
```

Verify the install:

```bash
kazi --version
# → KAZI OS v0.3.0
```

---

## Step 2: Set Your API Key

Create a `.env` file in the domain directory (or export to your shell):

```bash
export OPENAI_API_KEY=sk-your-key-here
```

KAZI OS uses OpenAI-compatible APIs. You can point it at any provider (Groq, Together, local models) by also setting:

```bash
export OPENAI_BASE_URL=https://api.openai.com/v1   # or your provider
```

---

## Step 3: Explore the Example Domain

```bash
cd examples/marcus-chen
ls
```

You will see:

```
identity.yaml       # Who is Marcus? What does he do?
voice.yaml          # How does he write?
guardrails.yaml     # What's banned? What's required?
council.yaml        # Who reviews the output?
manifest.yaml       # What pipelines exist?
templates/          # Output formatting
.env.example        # Required environment variables
```

Each file has one job. Together they define the entire content system.

---

## Step 4: Understand the Files

### identity.yaml

Defines who the agent is writing as. Background, methodology, positioning, and persistent context that should always be remembered.

```yaml
name: Marcus Chen
title: Executive Transition Coach
purpose: Help newly appointed leaders navigate their first 90 days

methodology:
  name: The Transition Framework
  phases:
    - name: Observe
      description: Map the political and operational landscape
    - name: Signal
      description: Deliver one visible early win
    - name: Anchor
      description: Build the coalition that sustains momentum
```

### voice.yaml

Defines how the agent writes. Tone, rhythm, narrative preferences, formatting rules per platform, and examples of "good" output.

```yaml
tone: direct, warm, occasionally blunt
perspective: first-person singular ("I") for posts

rhythm:
  - Vary sentence length. Short punches between longer explanations.
  - Lead with the insight, not the setup.

exemplars:
  - "The best leaders I've coached didn't try to prove themselves in week one."
```

### guardrails.yaml

Quality control. Banned words, banned patterns, and a pre-delivery checklist the agent must pass before output is final.

```yaml
banned_words:
  - journey
  - unlock
  - synergy
  - game-changer

pre_delivery_checklist:
  - "Does the opening line create a pattern interrupt?"
  - "Would Marcus actually say this out loud to a client?"
```

### council.yaml

On complex decisions, multiple advisory perspectives evaluate the draft before it ships.

```yaml
advisors:
  - id: practitioner
    role: The Coach
    question: "If I said this to a client in session, would they lean in or check out?"

  - id: skeptic
    role: The Contrarian
    question: "What would a cynical VP think reading this?"
```

### manifest.yaml

The operational blueprint. Defines pipelines (sequences of agents), triggers (when they run), and constraints (model, tokens, retry behavior).

```yaml
pipelines:
  weekly-post:
    stages:
      - agent: researcher
        role: "Research the topic, find relevant data points"
        goal: "Provide 3-5 specific facts related to the topic"

      - agent: drafter
        role: "Write the LinkedIn post in Marcus's voice"
        goal: "Produce a 150-300 word post with hook, body, and CTA"
        uses: [identity, voice, guardrails]

      - agent: council_review
        role: "Run the draft through the advisory council"
        uses: [council]

      - agent: editor
        role: "Final polish based on council feedback"
        uses: [voice, guardrails]
```

---

## Step 5: Validate (Dry Run)

Before spending tokens, validate the pipeline:

```bash
kazi run weekly-post --dry-run
```

Expected output:

```
  KAZI OS — Pipeline Runner
  ─────────────────────────
  Domain:      marcus-chen
  Pipeline:    weekly-post

  [DRY RUN] Pipeline validated successfully

  Model:       gpt-4.1-mini
  Stages:      4

    1. researcher
       Role: Research the topic, find relevant data points or trends
       Goal: Provide 3-5 specific facts, statistics, or patterns related to the topic

    2. drafter
       Role: Write the LinkedIn post in Marcus's voice
       Goal: Produce a 150-300 word post with hook, body, and CTA
       Uses: identity, voice, guardrails

    3. council_review
       Role: Run the draft through the advisory council
       Goal: Get alignment from at least 3 advisors, surface objections
       Uses: council

    4. editor
       Role: Final polish based on council feedback
       Goal: Produce publication-ready post that passes all guardrail checks
       Uses: voice, guardrails

  Domain files loaded:
    ✓ identity.yaml
    ✓ voice.yaml
    ✓ guardrails.yaml
    ✓ council.yaml
```

---

## Step 6: Run the Pipeline

```bash
kazi run weekly-post --input '{"topic": "Why most leadership transitions fail in the first 90 days"}' --verbose
```

What happens:

1. **Researcher** gathers facts and statistics about leadership transitions
2. **Drafter** writes a LinkedIn post using Marcus's voice, identity, and guardrails
3. **Council** (5 advisors) evaluates the draft from different perspectives
4. **Editor** polishes based on council feedback, ensures guardrails pass

Expected output:

```
  Status:      completed
  Model:       gpt-4.1-mini
  Tokens:      ~5,800
  Stages:      4

  ══════════════════════════════════════════════════
  FINAL OUTPUT
  ══════════════════════════════════════════════════

  Most leadership transitions fail in the first 90 days because
  new execs skip the map.

  I coached a leader who walked into a complex division and
  immediately launched a big initiative...

  [Full post, 150-300 words, in Marcus's voice]

  ══════════════════════════════════════════════════

  Saved to: output/weekly-post_20260528_025727.md
```

The output is saved to the `output/` directory automatically.

---

## Step 7: Iterate

To refine the system, edit the YAML files:

| Want to... | Edit this file |
|---|---|
| Change the writing style | `voice.yaml` |
| Add banned words or patterns | `guardrails.yaml` |
| Change who reviews output | `council.yaml` |
| Add a new pipeline | `manifest.yaml` |
| Update background context | `identity.yaml` |

Then run again. No code changes. No redeployment.

---

## Step 8: Add a Second Pipeline

The `manifest.yaml` already includes a `monthly-article` pipeline. Run it:

```bash
kazi run monthly-article --input '{"topic": "The Observe phase: why listening is strategy"}' --verbose
```

This runs a 5-stage pipeline (researcher, outliner, writer, council, editor) and produces a 500-800 word newsletter article.

---

## What You Built

A complete content production system defined in 5 YAML files:

- **No Python code** required from the user
- **Voice consistency** enforced by `voice.yaml`
- **Quality control** enforced by `guardrails.yaml`
- **Multi-perspective review** via `council.yaml`
- **Repeatable execution** via `manifest.yaml`
- **Automatic output saving** to `output/`

The user ships expertise as configuration. The platform handles execution.

---

## Next Steps

- **Customize for your domain**: Copy `examples/marcus-chen/`, rename it, and replace the YAML content with your own expertise
- **Add triggers**: Configure scheduled execution (e.g., "every Tuesday at 7am")
- **Add templates**: Create output templates in `templates/` for formatted delivery
- **Connect delivery**: Route output to Notion, email, or webhook (coming soon)

---

## Quick Reference

```bash
kazi init my-domain              # Scaffold a new domain
kazi run <pipeline> --dry-run    # Validate without executing
kazi run <pipeline> --input '{}'  # Execute with input
kazi run <pipeline> --verbose    # Show stage details
```
