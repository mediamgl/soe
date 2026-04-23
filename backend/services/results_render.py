"""
Results renderer — Phase 7.

Given the annotated deliverable + session, produce either a PDF (via WeasyPrint)
or a Markdown string. Shared Jinja2 template context ensures PDF and Markdown
render identical content.
"""
from __future__ import annotations
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from services import dimensions_catalogue as dims

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env_html = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "htm"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env_md = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


# --------------------------------------------------------------------------- #
# Context assembly — shared between the two renderers
# --------------------------------------------------------------------------- #
def _marker_percent(delta: float) -> float:
    """Map a calibration delta in [-2..+2] onto a 0..100% track position.
    Under-claiming (negative delta) is on the left; over-claiming on the right."""
    clipped = max(-2.0, min(2.0, float(delta)))
    # -2 → 0%, 0 → 50%, +2 → 100%
    return (clipped + 2.0) * 25.0


def _first_name(full_name: str) -> str:
    return (full_name or "Participant").strip().split(None, 1)[0]


def _completed_date(session: Dict[str, Any]) -> str:
    raw = session.get("completed_at") or session.get("updated_at") or session.get("created_at")
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d %B %Y")
    except Exception:
        return raw[:10]


def _inject_dimension_name_and_definition(deliverable: Dict[str, Any]) -> Dict[str, Any]:
    """Dimension profiles coming from the LLM carry dimension_id but not always
    the human name/definition. Inject these from the catalogue so templates
    can render without looking up the catalogue themselves."""
    for p in deliverable.get("dimension_profiles", []) or []:
        try:
            d = dims.by_id(p.get("dimension_id"))
            p["name"] = d.name
            p["cluster"] = d.cluster
            p["definition"] = d.definition
        except KeyError:
            p["name"] = p.get("name") or p.get("dimension_id", "").replace("_", " ").title()
            p["cluster"] = p.get("cluster") or ""
            p["definition"] = p.get("definition") or ""
    return deliverable


def build_context(session: Dict[str, Any], deliverable: Dict[str, Any], self_awareness: Dict[str, Any]) -> Dict[str, Any]:
    deliverable = _inject_dimension_name_and_definition(deliverable)
    participant = session.get("participant") or {}
    sa = dict(self_awareness or {})
    if sa.get("status") == "computed":
        sa["marker_percent"] = _marker_percent(sa.get("delta", 0.0))

    scenario_scores = ((session.get("scores") or {}).get("scenario") or {})
    strategic = {
        "cognitive_flexibility": scenario_scores.get("cognitive_flexibility"),
        "systems_thinking": scenario_scores.get("systems_thinking"),
        "additional_observations": scenario_scores.get("additional_observations"),
    }
    return {
        "cover": {
            "title": "Transformation Readiness Assessment",
            "completed_date": _completed_date(session),
        },
        "participant": {
            "first_name": _first_name(participant.get("name", "")),
            "organisation": participant.get("organisation") or None,
            "role": participant.get("role") or None,
        },
        "resume_code": session.get("resume_code", ""),
        "deliverable": deliverable,
        "self_awareness": sa,
        "strategic": strategic,
        "dimensions_assessed": [
            {"id": d.id, "name": d.name, "cluster": d.cluster,
             "weight_percent": d.weight_percent, "definition": d.definition}
            for d in dims.assessed()
        ],
        "dimensions_not_assessed": [
            {"id": d.id, "name": d.name, "cluster": d.cluster,
             "weight_percent": d.weight_percent, "definition": d.definition}
            for d in dims.not_assessed()
        ],
    }


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def render_markdown(context: Dict[str, Any]) -> str:
    tpl = _env_md.get_template("results.md.j2")
    return tpl.render(**context)


def render_html(context: Dict[str, Any]) -> str:
    tpl = _env_html.get_template("results.html.j2")
    return tpl.render(**context)


def render_pdf(context: Dict[str, Any]) -> bytes:
    # Import here so module import doesn't fail if WeasyPrint deps ever break.
    from weasyprint import HTML
    html_str = render_html(context)
    return HTML(string=html_str).write_pdf()


# --------------------------------------------------------------------------- #
# Filename sanitiser — used by Content-Disposition
# --------------------------------------------------------------------------- #
def safe_filename(first_name: str, ext: str) -> str:
    name = unicodedata.normalize("NFKD", first_name or "Participant")
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
    name = re.sub(r"\s+", "-", name.strip()) or "Participant"
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return f"TRA-{name}-{date_str}.{ext}"
