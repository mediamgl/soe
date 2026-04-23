"""
Conversation exporter — Phase 8 admin downloads.

Two formats, both admin-only:
  - Markdown: pretty, human-readable, suitable for paste into a briefing doc.
    Redacted sessions render with "(redacted)" participant and omit email.
  - JSON: the raw conversation array with all _meta (timestamps, provider,
    model, latency_ms, fallbacks_tried, turn). Pretty-printed.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, List, Tuple


def _fmt_ts(ts: Any) -> str:
    if not ts or not isinstance(ts, str):
        return ""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts[:19]


def _participant_label(session: Dict[str, Any]) -> str:
    p = session.get("participant") or {}
    if session.get("redacted"):
        return "(redacted) · session " + str(session.get("session_id", ""))[:8]
    name = p.get("name") or "Participant"
    org = p.get("organisation")
    role = p.get("role")
    parts = [name]
    if org:
        parts.append(org)
    if role:
        parts.append(role)
    return " · ".join(parts)


def to_markdown(session: Dict[str, Any]) -> str:
    conv = session.get("conversation") or []
    hdr = _participant_label(session)
    lines: List[str] = []
    lines.append("# AI Fluency Discussion — " + hdr)
    lines.append("")
    lines.append("- **Session ID:** `" + str(session.get("session_id", "")) + "`")
    if session.get("completed_at"):
        lines.append("- **Completed:** " + _fmt_ts(session.get("completed_at")))
    elif session.get("created_at"):
        lines.append("- **Created:** " + _fmt_ts(session.get("created_at")))
    ai = (session.get("ai_discussion") or {})
    if ai.get("user_turn_count") is not None:
        lines.append("- **User turns:** " + str(ai.get("user_turn_count")))
    lines.append("")
    lines.append("---")
    lines.append("")

    if not conv:
        lines.append("*(no conversation recorded)*")
        return "\n".join(lines) + "\n"

    for i, turn in enumerate(conv):
        role = turn.get("role", "unknown")
        content = turn.get("content", "") or ""
        t = turn.get("turn", "")
        ts = _fmt_ts(turn.get("timestamp"))
        provider = turn.get("provider")
        model = turn.get("model")
        latency = turn.get("latency_ms")
        fallbacks = turn.get("fallbacks_tried")

        if role == "assistant":
            header = "## Interviewer"
        elif role == "user":
            header = "## Participant"
        else:
            header = "## " + role.capitalize()
        meta_bits: List[str] = []
        if t != "":
            meta_bits.append("turn " + str(t))
        if ts:
            meta_bits.append(ts)
        if meta_bits:
            header += " *(" + ", ".join(meta_bits) + ")*"
        lines.append(header)
        lines.append("")
        lines.append(content.strip() or "*(empty)*")
        lines.append("")
        # Admin-only meta trailer
        if role == "assistant" and (provider or model or latency is not None):
            trailer_bits = []
            if provider:
                trailer_bits.append("provider=`" + str(provider) + "`")
            if model:
                trailer_bits.append("model=`" + str(model) + "`")
            if latency is not None:
                trailer_bits.append("latency=" + str(latency) + "ms")
            if fallbacks is not None:
                trailer_bits.append("fallbacks_tried=" + str(fallbacks))
            lines.append("> *_meta — " + " · ".join(trailer_bits) + "_*")
            lines.append("")
        if i < len(conv) - 1:
            lines.append("---")
            lines.append("")

    # Footer with scoring summary (admin convenience)
    ai_scores = (session.get("scores") or {}).get("ai_fluency") or {}
    if ai_scores:
        lines.append("---")
        lines.append("")
        lines.append("### Scoring summary")
        overall = ai_scores.get("overall_score")
        if overall is not None:
            lines.append("- Overall: **" + str(overall) + "**")
        comps = (ai_scores.get("components") or {})
        for k, v in comps.items():
            if isinstance(v, dict):
                lines.append("- " + k.replace("_", " ").title() + ": " + str(v.get("score")) + " (" + str(v.get("confidence")) + ")")
        strengths = ai_scores.get("strengths") or []
        if strengths:
            lines.append("")
            lines.append("**Strengths:**")
            for s in strengths:
                lines.append("- " + str(s))
        blind = ai_scores.get("blind_spots") or []
        if blind:
            lines.append("")
            lines.append("**Blind spots:**")
            for s in blind:
                lines.append("- " + str(s))
    return "\n".join(lines) + "\n"


def to_json(session: Dict[str, Any]) -> str:
    """Pretty JSON of the raw conversation array + scoring metadata."""
    out = {
        "session_id": session.get("session_id"),
        "redacted": bool(session.get("redacted")),
        "participant_label": _participant_label(session),
        "completed_at": session.get("completed_at"),
        "conversation": session.get("conversation") or [],
        "scoring": (session.get("scores") or {}).get("ai_fluency"),
    }
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def filename_for(session: Dict[str, Any], ext: str) -> str:
    """Sanitised filename: TRA-conversation-{label}-{YYYY-MM-DD}.{ext}."""
    import re
    import unicodedata
    p = session.get("participant") or {}
    label = "session-" + str(session.get("session_id", ""))[:8] if session.get("redacted") else (p.get("name") or "participant")
    label = unicodedata.normalize("NFKD", label)
    label = "".join(c for c in label if c.isalnum() or c in ("-", "_", " "))
    label = re.sub(r"\s+", "-", label.strip()) or "session"
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return "TRA-conversation-" + label + "-" + date_str + "." + ext
