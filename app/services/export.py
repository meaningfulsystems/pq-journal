"""Export journal entries to Markdown or PDF."""
from __future__ import annotations

from datetime import datetime


def to_markdown(entry: dict) -> str:
    title = entry.get("title", "Untitled")
    created = entry.get("created", "")
    tags = entry.get("tags", [])
    overall_emotion = entry.get("overall_emotion", "")
    paragraphs = entry.get("paragraphs", [])
    body = entry.get("body", "")

    lines = [f"# {title}", ""]

    # Metadata block
    if created:
        try:
            dt = datetime.fromisoformat(created)
            lines.append(f"**Date:** {dt.strftime('%B %d, %Y %H:%M')}")
        except Exception:
            lines.append(f"**Date:** {created}")
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
    if overall_emotion:
        lines.append(f"**Overall Emotion:** {overall_emotion}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Paragraphs with emotion annotations if available
    if paragraphs:
        for para in paragraphs:
            text = para.get("text", "").strip()
            if not text:
                continue
            lines.append(text)
            emotion_label = para.get("emotion_label", "")
            if emotion_label:
                lines.append(f"*{emotion_label}*")
            lines.append("")
    elif body:
        lines.append(body)
        lines.append("")

    return "\n".join(lines)


def to_pdf(entry: dict) -> bytes:
    """Convert entry to PDF. Requires weasyprint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError("weasyprint is not installed. Run: pip install weasyprint")

    md_content = to_markdown(entry)

    # Convert Markdown to HTML (basic, without a full MD library)
    html_lines = ["<!DOCTYPE html><html><head>",
                  "<style>body{font-family:Georgia,serif;max-width:700px;margin:40px auto;line-height:1.7;color:#111;}",
                  "h1{font-size:2em;margin-bottom:0.2em;}",
                  "em{color:#555;font-size:0.9em;}",
                  "hr{border:none;border-top:1px solid #ddd;margin:1.5em 0;}",
                  "</style></head><body>"]

    for line in md_content.splitlines():
        if line.startswith("# "):
            html_lines.append(f"<h1>{_escape(line[2:])}</h1>")
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f"<p><strong>{_escape(line[2:-2])}</strong></p>")
        elif line == "---":
            html_lines.append("<hr>")
        elif line.startswith("*") and line.endswith("*"):
            html_lines.append(f"<p><em>{_escape(line[1:-1])}</em></p>")
        elif line.strip():
            html_lines.append(f"<p>{_escape(line)}</p>")

    html_lines.append("</body></html>")
    html_content = "\n".join(html_lines)

    return HTML(string=html_content).write_pdf()


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
