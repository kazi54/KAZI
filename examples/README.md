# Scenarios

This document shows how real people use KAZI to build intelligence products. Each scenario describes who the person is, what they want, and exactly how KAZI's pieces fit together to deliver it.

---

## Scenario 1: Weekly News Brief

**Who:** A management consultant tracking the electric vehicle industry for her clients.

**What she wants:** Every Monday morning, a scored and filtered digest of the most important EV news from the past week, delivered to her inbox as a formatted PDF.

**How KAZI does it:**

```
Pipeline: news-scout → relevance-scorer → brief-compiler → email-delivery
Trigger:  ScheduledTrigger(cron="0 7 * * 1")  # Monday 7 AM
```

| Component | What it does |
|-----------|-------------|
| `NewsScout` agent | Calls NewsAPI + RSS feeds for "electric vehicles", "EV battery", "charging infrastructure". Returns 50-100 raw articles. |
| `RelevanceScorer` agent | Scores each article on 3 dimensions: `timeliness` (how recent), `source_authority` (Reuters > random blog), `topic_match` (how closely it matches her defined topics). |
| `scoring.yaml` | Tiers: Noise (0-40) → Monitor (40-60) → Include (60-80) → Lead Story (80-100). Only articles scoring 60+ make it into the brief. |
| `BriefCompiler` agent | Takes the top 10 scored articles, summarizes each in 2-3 sentences, groups by sub-topic, renders into `weekly_brief.html` template. |
| Delivery | Sends the rendered PDF to her email via SendGrid. |

**What she wrote:** 2 agents (~50 lines each), 1 scoring.yaml (15 lines), 1 HTML template.
**What KAZI handled:** Scheduling, pipeline execution, scoring logic, template rendering, retry on API failures.

---

## Scenario 2: Competitive Intelligence Dashboard

**Who:** A startup founder who needs to track 5 competitors across funding announcements, key hires, product launches, and press mentions.

**What he wants:** A live dashboard showing scored signals per competitor, updated daily. High-urgency signals (new funding round, executive hire) trigger an immediate Slack notification.

**How KAZI does it:**

```
Pipeline: signal-scout → signal-scorer → dashboard-writer
Trigger:  ScheduledTrigger(cron="0 6 * * *")  # Daily 6 AM
Event:    EventTrigger(event="score_above_80", action="notify_slack")
```

| Component | What it does |
|-----------|-------------|
| `SignalScout` agent | Searches Crunchbase API, Google News, LinkedIn (via proxy), and SEC filings for each competitor. Uses FanOut to run all 5 competitors in parallel. |
| `SignalScorer` agent | Scores each signal on: `impact` (funding > blog post), `recency` (today > last week), `confidence` (primary source > rumor). |
| `scoring.yaml` | Tiers: Background (0-40) → Noteworthy (40-60) → Important (60-80) → Urgent (80-100). |
| `DashboardWriter` agent | Writes scored signals to the database. Dashboard frontend reads from the same store. |
| Event trigger | When any signal scores 80+, fires a Slack webhook with a one-line summary. |

**What he wrote:** 2 agents, 1 scoring.yaml, 1 Slack webhook config, a simple React dashboard page.
**What KAZI handled:** Parallel execution across 5 competitors, scoring, event detection, database writes, scheduling.

---

## Scenario 3: Content Calendar for a Thought Leader

**Who:** A thought leader who publishes weekly articles. She needs a system that surfaces trending topics in her domain, scores them for relevance to her audience, and maintains a running content calendar.

**What she wants:** Every Wednesday, a ranked list of 5 topic suggestions with source links, audience fit score, and a one-paragraph angle for each. Delivered as a Notion page (or email).

**How KAZI does it:**

```
Pipeline: topic-scout → topic-scorer → angle-writer → calendar-updater
Trigger:  ScheduledTrigger(cron="0 9 * * 3")  # Wednesday 9 AM
```

| Component | What it does |
|-----------|-------------|
| `TopicScout` agent | Searches Google Trends, Twitter/X trending, arxiv preprints, and industry newsletters for topics matching her domain keywords. |
| `TopicScorer` agent | Scores each topic on: `trending_velocity` (how fast it's growing), `audience_fit` (does her audience care), `uniqueness` (has she already covered this), `timeliness` (is there a news hook). |
| `scoring.yaml` | Tiers: Skip (0-40) → Maybe (40-60) → Write (60-80) → Priority (80-100). Top 5 topics scoring 50+ get passed forward. |
| `AngleWriter` agent | For each topic, generates a one-paragraph "angle" — how she could approach it differently from what's already published. Uses LLM with her past articles as context. |
| `CalendarUpdater` agent | Writes the suggestions to her Notion database (or sends via email). |

**What she wrote:** 3 agents, 1 scoring.yaml, 1 Notion integration config.
**What KAZI handled:** Scheduling, multi-source crawling, scoring, LLM calls with retry, delivery.

---

## Scenario 4: Client Account Monitoring

**Who:** An account manager at a consulting firm responsible for 20 enterprise clients. She needs to know when something significant happens at any of her accounts (leadership change, earnings miss, acquisition, layoff).

**What she wants:** Real-time alerts when a client appears in news with a material event. A weekly summary of all client activity, sorted by urgency.

**How KAZI does it:**

```
Pipeline: client-monitor → event-classifier → alert-router
Trigger:  ScheduledTrigger(cron="0 */4 * * *")  # Every 4 hours
FanOut:   20 clients in parallel
```

| Component | What it does |
|-----------|-------------|
| `ClientMonitor` agent | For each of 20 clients, searches news APIs and SEC filings. FanOut runs all 20 in parallel. |
| `EventClassifier` agent | Classifies each mention into event types: `leadership_change`, `financial_event`, `product_launch`, `legal`, `partnership`. Scores on `materiality` and `urgency`. |
| `scoring.yaml` | Tiers: Routine (0-40) → Notable (40-60) → Action Required (60-80) → Escalate Now (80-100). |
| `AlertRouter` agent | Scores 60+ → Slack DM immediately. All scores → weekly digest email every Friday. |

**What she wrote:** 2 agents, 1 scoring.yaml, routing config (Slack + email).
**What KAZI handled:** Parallel monitoring of 20 accounts, classification, scoring, conditional routing, weekly aggregation.

---

## The Pattern

Every scenario follows the same structure:

```
Scout (find signals) → Score (evaluate relevance) → Act (compile + deliver)
```

What changes between scenarios is:

| Part | You define | KAZI provides |
|------|-----------|---------------|
| **Sources** | Which APIs, feeds, databases to search | Tool abstraction, retry, rate limiting |
| **Scoring rubric** | What dimensions matter, what thresholds to use | Scoring engine, tier classification, confidence decay |
| **Output format** | HTML template, Slack message, database write | Template rendering, delivery routing |
| **Schedule** | How often to run | Cron triggers, event triggers, on-demand |
| **Scale** | How many entities to track | FanOut parallel execution |

You bring the domain expertise. KAZI brings the engine.

---

## Getting Started with Your Scenario

```bash
# 1. Clone and install
git clone https://github.com/kazi54/KAZI.git
cd KAZI && pip install -e .

# 2. Create your domain
kazi init my-domain

# 3. Define your pipeline in domains/my-domain/manifest.yaml
# 4. Write your agents in domains/my-domain/agents/
# 5. Configure scoring in domains/my-domain/scoring.yaml
# 6. Create your output template in domains/my-domain/templates/

# 7. Run it
kazi run my-domain
```

See [Getting Started](../docs/getting-started.md) for the full walkthrough, or [Building Agents](../docs/building-agents.md) for agent implementation details.
