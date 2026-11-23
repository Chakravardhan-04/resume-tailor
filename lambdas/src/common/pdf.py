"""Render the tailored result as a PDF (reportlab, pure Python)."""

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    # LLM text is untrusted: escape so stray <, & never break (or inject into) the markup.
    return Paragraph(escape(text), style)


def build_pdf(result: dict[str, Any]) -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=14)
    h1 = ParagraphStyle("H1", parent=styles["Title"], fontSize=20, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#1f3a5f"), spaceBefore=14
    )
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, textColor=colors.grey)

    story: list[Any] = [
        _p("Tailored Resume Draft", h1),
        _p(f"Match score: {result['score']}/100", body),
        _p("Summary", h2),
        _p(result["summary"], body),
        _p("Tailored Experience Bullets", h2),
        ListFlowable(
            [ListItem(_p(b, body), leftIndent=14) for b in result["bullets"]],
            bulletType="bullet",
            start="\u2022",
        ),
        _p("Gap List", h2),
        _p("Requirements from the job description that your resume does not yet demonstrate.", small),
        Spacer(1, 4),
    ]

    if result["gaps"]:
        items = []
        for gap in result["gaps"]:
            label = "Must have" if gap["category"] == "must_have" else "Nice to have"
            items.append(ListItem(_p(f"{gap['requirement']} ({label}): {gap['reason']}", body), leftIndent=14))
        story.append(ListFlowable(items, bulletType="bullet", start="\u2022"))
    else:
        story.append(_p("No gaps found. Every stated requirement is supported by your resume.", body))

    story += [
        Spacer(1, 18),
        _p(
            "AI-generated draft. Contains only facts from your original resume; review before sending to employers.",
            small,
        ),
    ]

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="Tailored Resume Draft",
    ).build(story)
    return buffer.getvalue()
