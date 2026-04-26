"""
Results renderer — Phase 7.

Given the annotated deliverable + session, produce either a PDF (via WeasyPrint)
or a Markdown string. Shared Jinja2 template context ensures PDF and Markdown
render identical content.
"""
from __future__ import annotations
import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

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


# --------------------------------------------------------------------------- #
# Radar SVG (server-side, embedded in PDF — mirrors the admin radar geometry)
# --------------------------------------------------------------------------- #
RADAR_AXIS_ORDER: Tuple[str, ...] = (
    "learning_agility",
    "tolerance_for_ambiguity",
    "cognitive_flexibility",
    "self_awareness_accuracy",
    "ai_fluency",
    "systems_thinking",
)


def _wrap_label(dim_id: str) -> List[str]:
    """Mirror of the admin chart's wrapping rule. 1 word → one line; 2 words →
    two lines; 3+ words → first n-1 words on line 1, last word on line 2."""
    words = dim_id.replace("_", " ").upper().split(" ")
    if len(words) <= 1:
        return [words[0]]
    if len(words) == 2:
        return [words[0], words[1]]
    return [" ".join(words[:-1]), words[-1]]


def _build_radar_svg(deliverable: Dict[str, Any]) -> str:
    """Generate an inline SVG radar chart from the 6 dimension scores. Same
    palette / axis order / wrapping logic as the admin RadarChart so the PDF
    looks identical to what the admin sees on screen.

    Returns an HTML-safe SVG string. Returns "" if no dimension_profiles."""
    profiles = (deliverable.get("dimension_profiles") or [])
    if not profiles:
        return ""
    by_id = {p.get("dimension_id"): p.get("score") for p in profiles}
    size = 220
    cx = cy = size / 2
    r = 82
    label_r = r + 20
    line_h = 9.5

    n = len(RADAR_AXIS_ORDER)
    axes = []
    for i, dim_id in enumerate(RADAR_AXIS_ORDER):
        angle = (-math.pi / 2) + (i / n) * math.pi * 2
        score = by_id.get(dim_id) or 0.0
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        # Clamp to 0..5
        score = max(0.0, min(5.0, score))
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        sx = cx + (score / 5.0) * r * math.cos(angle)
        sy = cy + (score / 5.0) * r * math.sin(angle)
        lx = cx + label_r * math.cos(angle)
        ly = cy + label_r * math.sin(angle)
        cosa = math.cos(angle)
        anchor = "start" if cosa > 0.15 else ("end" if cosa < -0.15 else "middle")
        lines = _wrap_label(dim_id)
        axes.append({
            "x": x, "y": y, "sx": sx, "sy": sy, "lx": lx, "ly": ly,
            "angle": angle, "anchor": anchor, "lines": lines,
        })

    # ViewBox matches the admin chart's canvas so labels never clip.
    vb_x, vb_y, vb_w, vb_h = -90, -30, size + 180, size + 60

    def _fmt(v: float) -> str:
        # Compact float — enough precision for SVG, no trailing noise.
        return f"{v:.2f}"

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x} {vb_y} {vb_w} {vb_h}" '
        f'width="320" height="240" '
        f'role="img" aria-label="Dimension radar — visual summary of six assessed dimensions">'
    )

    # Concentric scale polygons
    for scale in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(
            f"{_fmt(cx + scale * r * math.cos(a['angle']))},{_fmt(cy + scale * r * math.sin(a['angle']))}"
            for a in axes
        )
        parts.append(
            f'<polygon points="{pts}" fill="none" stroke="#1e3a5f" stroke-opacity="0.10"/>'
        )

    # Axis lines
    for a in axes:
        parts.append(
            f'<line x1="{_fmt(cx)}" y1="{_fmt(cy)}" x2="{_fmt(a["x"])}" y2="{_fmt(a["y"])}" '
            f'stroke="#1e3a5f" stroke-opacity="0.15"/>'
        )

    # Score polygon — gold fill at 30%, navy stroke (per spec)
    poly_pts = " ".join(f'{_fmt(a["sx"])},{_fmt(a["sy"])}' for a in axes)
    parts.append(
        f'<polygon points="{poly_pts}" fill="#d4a84b" fill-opacity="0.30" '
        f'stroke="#1e3a5f" stroke-width="1.5"/>'
    )

    # Labels
    for a in axes:
        start_dy = -line_h / 2 if len(a["lines"]) == 2 else 0
        tspans = []
        for idx, line in enumerate(a["lines"]):
            dy = start_dy if idx == 0 else line_h
            tspans.append(
                f'<tspan x="{_fmt(a["lx"])}" dy="{_fmt(dy)}">{line}</tspan>'
            )
        parts.append(
            f'<text x="{_fmt(a["lx"])}" y="{_fmt(a["ly"])}" '
            f'font-size="8.5" fill="#6b7280" '
            f'text-anchor="{a["anchor"]}" dominant-baseline="middle" '
            f'letter-spacing="1" font-family="Inter, Helvetica, Arial, sans-serif">'
            f'{"".join(tspans)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


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
        # Pre-rendered SVG injected verbatim into results.html.j2; |safe in
        # the template. Empty string when no dimension_profiles, in which
        # case the template renders nothing in that slot.
        "radar_svg": Markup(_build_radar_svg(deliverable)),
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
