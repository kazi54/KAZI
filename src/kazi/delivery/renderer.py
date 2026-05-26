"""
Template Renderer — Domain-agnostic Jinja2 rendering engine.

Loads templates from any domain's templates/ directory, renders with
pipeline context, and converts to multiple output formats.

Supported output formats:
  - HTML (native Jinja2)
  - Markdown (native Jinja2 with .md templates)
  - JSON (native Jinja2 with .json templates)
  - PDF (HTML → WeasyPrint or xhtml2pdf)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


# ─── Custom Filters ───────────────────────────────────────────────────────────

_custom_filters: dict[str, Callable] = {}


def register_filter(name: str):
    """Decorator to register a custom Jinja2 filter."""
    def decorator(func: Callable) -> Callable:
        _custom_filters[name] = func
        return func
    return decorator


# Built-in filters
@register_filter("score_color")
def _score_color(score: float) -> str:
    """Map a score to a hex color."""
    if score >= 7.5:
        return "#4ade80"
    if score >= 5.5:
        return "#fbbf24"
    if score >= 3.5:
        return "#fb923c"
    return "#ef4444"


@register_filter("tier_badge")
def _tier_badge(tier: str) -> str:
    """Map a tier name to a styled badge class."""
    return f"tier-{tier.lower()}"


# ─── Renderer ─────────────────────────────────────────────────────────────────


class TemplateRenderer:
    """
    Renders templates with pipeline context data.

    Usage:
        renderer = TemplateRenderer(templates_dir="domains/content/templates")
        html = renderer.render("report_v1.html", context={...})
        pdf_bytes = renderer.render_pdf("report_v1.html", context={...})
    """

    def __init__(self, templates_dir: str):
        self._templates_dir = Path(templates_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Register all custom filters
        for name, func in _custom_filters.items():
            self._env.filters[name] = func

    def render(self, template_name: str, context: dict) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Filename relative to templates_dir (e.g., "report_v1.html")
            context: Template variables (scored_findings, org_id, run_id, etc.)

        Returns:
            Rendered string (HTML, Markdown, JSON, etc.)
        """
        template = self._env.get_template(template_name)
        rendered = template.render(**context)
        logger.debug(f"Rendered template: {template_name} ({len(rendered)} chars)")
        return rendered

    def render_to_file(self, template_name: str, context: dict, output_path: str) -> str:
        """Render a template and write to a file. Returns the output path."""
        rendered = self.render(template_name, context)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(rendered)
        logger.info(f"Rendered to file: {output_path}")
        return output_path

    def render_pdf(self, template_name: str, context: dict, output_path: str) -> str:
        """
        Render an HTML template and convert to PDF.

        Requires weasyprint or xhtml2pdf to be installed.
        Falls back gracefully if neither is available.
        """
        html_content = self.render(template_name, context)

        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(output_path)
            logger.info(f"PDF generated (weasyprint): {output_path}")
            return output_path
        except ImportError:
            pass

        try:
            from xhtml2pdf import pisa
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                pisa_status = pisa.CreatePDF(html_content, dest=f)
                if pisa_status.err:
                    raise RuntimeError(f"xhtml2pdf error: {pisa_status.err}")
            logger.info(f"PDF generated (xhtml2pdf): {output_path}")
            return output_path
        except ImportError:
            raise RuntimeError(
                "PDF generation requires 'weasyprint' or 'xhtml2pdf'. "
                "Install with: pip install weasyprint  OR  pip install xhtml2pdf"
            )

    def render_multi_format(
        self,
        context: dict,
        formats: list[dict],
        output_dir: str,
    ) -> list[dict]:
        """
        Render multiple formats from a single context.

        Args:
            context: Template variables
            formats: List of {"template": "...", "format": "html|pdf|md|json", "filename": "..."}
            output_dir: Directory for output files

        Returns:
            List of {"format": ..., "path": ..., "size_bytes": ...}
        """
        results = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for fmt in formats:
            template_name = fmt["template"]
            file_format = fmt.get("format", "html")
            filename = fmt.get("filename", f"output.{file_format}")
            dest = str(output_path / filename)

            if file_format == "pdf":
                self.render_pdf(template_name, context, dest)
            else:
                self.render_to_file(template_name, context, dest)

            size = Path(dest).stat().st_size
            results.append({
                "format": file_format,
                "path": dest,
                "size_bytes": size,
                "template": template_name,
            })

        logger.info(f"Multi-format render complete: {len(results)} files in {output_dir}")
        return results

    def detect_format(self, template_name: str) -> str:
        """Detect output format from template file extension."""
        suffix = Path(template_name).suffix.lower()
        format_map = {
            ".html": "html",
            ".htm": "html",
            ".md": "markdown",
            ".json": "json",
            ".xml": "xml",
            ".txt": "text",
        }
        return format_map.get(suffix, "html")

    def list_templates(self) -> list[dict]:
        """List all available templates with metadata."""
        templates = []
        for path in self._templates_dir.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                templates.append({
                    "name": str(path.relative_to(self._templates_dir)),
                    "format": self.detect_format(path.name),
                    "size_bytes": path.stat().st_size,
                })
        return templates
