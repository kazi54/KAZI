# Templates

The template system is KAZI OS's delivery layer. It transforms structured agent output into polished, client-ready documents — HTML reports, PDF deliverables, email briefs, and dashboards.

---

## How Templates Work

```
Agent Output (dict) → Template Engine (Jinja2) → Rendered HTML → Delivery (PDF, email, dashboard)
```

Templates are HTML files with Jinja2 variables. The `CompileAgent` passes accumulated pipeline data into the template, and the renderer produces the final deliverable.

---

## Template Structure

Every template follows a consistent structure:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{report_title}}</title>
    <style>
        /* Self-contained styles — no external dependencies */
    </style>
</head>
<body>
    <!-- Cover -->
    <section class="cover">
        <h1>{{report_title}}</h1>
        <p>{{client_name}} · {{date}}</p>
    </section>

    <!-- Sections -->
    <section class="section" id="s01">
        <h2>{{section_01_title}}</h2>
        {{section_01_content}}
    </section>

    <!-- Score Grid -->
    <section class="score-grid">
        {% for dim_name, dim_score in scores.dimensions.items() %}
        <div class="score-cell" style="background: {{legend.classify(dim_score).color}}20">
            <span class="score-value">{{dim_score}}</span>
            <span class="score-label">{{dim_name | title}}</span>
        </div>
        {% endfor %}
    </section>
</body>
</html>
```

---

## Template Conventions

### File Naming

```
templates/
├── audit_report_v2.html       # Versioned — never overwrite, always increment
├── pathway_report_v2.html
├── playbook_report_v2.html
├── monitoring_report.html
├── weekly_brief.html
└── _partials/
    ├── _cover.html            # Reusable partial (prefixed with underscore)
    ├── _score_grid.html
    └── _legend.html
```

### Self-Contained

Templates must be fully self-contained — all CSS is inline, no external stylesheets, no JavaScript dependencies. This ensures the rendered HTML displays correctly in any context (email, PDF, browser, print).

### Print-Ready

All templates include print/PDF break markers:

```html
<div style="page-break-before: always;"></div>
```

Place breaks between major sections so the document prints cleanly on A4/Letter paper.

### Dark Theme Default

KAZI OS templates use a dark theme by default (matching the dashboard aesthetic):

```css
:root {
    --bg-primary: #0f1419;
    --bg-secondary: #1a2332;
    --text-primary: #e8eaed;
    --text-secondary: #9aa0a6;
    --accent: #4ade80;        /* Green — matches KAZI brand */
    --accent-warn: #f59e0b;
    --accent-danger: #ef4444;
    --accent-info: #06b6d4;
}
```

---

## Variable Reference

Templates receive a flat dictionary of variables from the `CompileAgent`. Standard variables available to all templates:

| Variable | Type | Description |
|----------|------|-------------|
| `report_title` | string | Full title of the report |
| `report_id` | string | Unique engagement ID (e.g., CRT-AUD-2026-0001) |
| `client_name` | string | Client organization name |
| `client_contact` | string | Client contact person |
| `date_generated` | string | ISO date of generation |
| `tier_name` | string | Engagement tier (Audit, Pathway, Playbook) |
| `scores` | dict | `{dimensions: {}, overall_score: float, tier: string}` |
| `legend` | object | ScoreLegend instance for tier lookups |
| `sections` | list | Ordered list of section content blocks |

Domain-specific variables are defined in the domain's `manifest.yaml` under `templates.variables`.

---

## Jinja2 Features

### Conditionals

```html
{% if scores.overall_score >= 80 %}
<div class="highlight fast-track">
    <strong>FAST-TRACK RECOMMENDED</strong>
</div>
{% elif scores.overall_score >= 60 %}
<div class="highlight pursue">
    <strong>PURSUE</strong>
</div>
{% endif %}
```

### Loops

```html
<table>
    <thead>
        <tr><th>Company</th><th>Fit Score</th><th>Rationale</th></tr>
    </thead>
    <tbody>
        {% for candidate in licensees %}
        <tr>
            <td>{{candidate.name}}</td>
            <td>{{candidate.fit_score}}/100</td>
            <td>{{candidate.rationale}}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
```

### Filters

```html
<!-- Format numbers -->
<span>{{market_size | format_currency}}</span>    <!-- $2.4B -->
<span>{{score | round(1)}}</span>                 <!-- 72.5 -->

<!-- Format dates -->
<span>{{date_generated | format_date}}</span>     <!-- May 6, 2026 -->

<!-- Truncate long text -->
<p>{{abstract | truncate(200)}}</p>
```

### Partials (Includes)

```html
<!-- Include reusable components -->
{% include '_partials/_cover.html' %}
{% include '_partials/_score_grid.html' %}
{% include '_partials/_legend.html' %}
```

---

## HITL Markers

Templates support Human-in-the-Loop markers — visual indicators that flag sections written or reviewed by a human expert (not AI-generated):

```html
<section class="section hitl-reviewed">
    <div class="hitl-badge">
        <span class="hitl-icon">✎</span>
        <span class="hitl-label">Expert-reviewed</span>
    </div>
    <h2>Strategy Memo</h2>
    {{strategy_memo_content}}
</section>
```

CSS for HITL markers:

```css
.hitl-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: var(--accent);
    color: var(--bg-primary);
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
}
```

---

## The Template Renderer

The `TemplateRenderer` class handles rendering:

```python
from kazi.delivery import TemplateRenderer

renderer = TemplateRenderer(template_dir="templates/")

# Render to HTML
html = renderer.render(
    template="audit_report_v2.html",
    data={
        "report_title": "CARTA Audit — Distributed Oxide Lens",
        "client_name": "Lumentum Operations LLC",
        "scores": {"overall_score": 72, "dimensions": {...}},
        ...
    }
)

# Convert to PDF
pdf_bytes = renderer.to_pdf(html)

# Save
renderer.save(html, path="output/report.html")
renderer.save(pdf_bytes, path="output/report.pdf")
```

---

## Creating a New Template

### Step 1: Define the Template Skeleton

Start from the base template or copy an existing one:

```bash
cp domains/_template/templates/base_report.html domains/my-domain/templates/my_report.html
```

### Step 2: Define Variables

Document what data the template expects in your `manifest.yaml`:

```yaml
templates:
  my_report:
    file: templates/my_report.html
    variables:
      - name: report_title
        type: string
        required: true
      - name: findings
        type: array
        required: true
      - name: recommendation
        type: string
        required: true
```

### Step 3: Build the HTML

Write the template using Jinja2 syntax. Follow the conventions:
- Self-contained CSS (no external deps)
- Print breaks between major sections
- Score grid uses legend colors
- HITL markers on human-reviewed sections

### Step 4: Test with Sample Data

Create a mockup script that renders the template with realistic sample data:

```python
from kazi.delivery import TemplateRenderer

renderer = TemplateRenderer(template_dir="templates/")

sample_data = {
    "report_title": "Sample Report",
    "findings": [
        {"title": "Finding 1", "detail": "..."},
        {"title": "Finding 2", "detail": "..."},
    ],
    "recommendation": "Proceed with licensing",
}

html = renderer.render("my_report.html", sample_data)
renderer.save(html, "mockups/my_report_mockup.html")
```

### Step 5: Version It

When making changes to a production template, create a new version rather than modifying in place:

```
my_report.html      → my_report_v2.html
```

Update the manifest to point to the new version. Old reports continue to reference the old template for reproducibility.

---

## Template Design Guidelines

| Principle | Implementation |
|-----------|---------------|
| Scannable | Use clear section headers, score grids, and visual hierarchy |
| Actionable | Every section should answer "so what?" — include recommendations |
| Printable | Test at A4/Letter, verify page breaks don't split tables |
| Accessible | Sufficient color contrast, semantic HTML, readable font sizes |
| Branded | Consistent use of KAZI green (#4ade80) for accents and tier indicators |
| Versioned | Never overwrite — increment version numbers |

---

## Delivery Formats

The template system supports multiple output formats from a single HTML source:

| Format | Method | Use case |
|--------|--------|----------|
| HTML | Direct render | Dashboard viewing, email embedding |
| PDF | WeasyPrint conversion | Formal delivery, printing, archival |
| Email | HTML with inline styles | Weekly briefs, notifications |
| Dashboard card | Extracted summary section | Quick-view in the platform UI |

```python
# All formats from one template
html = renderer.render("weekly_brief.html", data)
pdf = renderer.to_pdf(html)
email_html = renderer.to_email(html)  # Inlines all CSS for email clients
summary = renderer.extract_summary(html, selector=".executive-summary")
```
