"""Relatório FCT em PDF via reportlab (platypus), layout vindo de `report_template.yaml`.

Mesma identidade visual e mesma regra dos outros dois formatos
(`excel_report.py`, `word_report.py`): o resultado avaliado pelo operador é
apenas realçado na cor semântica correspondente, nunca calculado aqui.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import BrandingConfig
from reports.report_data import ReportData
from reports.template_engine import (
    build_context,
    evenly_sampled,
    load_template,
    render_fields,
    report_filename,
    result_color_hex,
)


def _fields_table(fields: list[tuple[str, str]]) -> Table:
    table = Table([[label, value] for label, value in fields], colWidths=[2.2 * inch, 3.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _data_table(columns: list[str], rows: list[list[str]], branding: BrandingConfig) -> Table:
    table = Table([columns] + rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(branding.color_primary_navy)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(branding.color_text_on_navy)),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    return table


def generate_pdf_report(data: ReportData, branding: BrandingConfig, output_dir: Path) -> Path:
    template = load_template()
    context = build_context(data, branding)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "FctTitle", parent=styles["Title"], textColor=colors.HexColor(branding.color_primary_navy)
    )
    heading_style = ParagraphStyle(
        "FctHeading", parent=styles["Heading2"], textColor=colors.HexColor(branding.color_secondary_navy)
    )
    subtitle_style = ParagraphStyle("FctSubtitle", parent=styles["Italic"])
    footer_style = ParagraphStyle("FctFooter", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / report_filename(data, "pdf")
    doc = SimpleDocTemplate(str(output_path), pagesize=A4)

    elements: list = []
    if branding.logo_path.exists():
        elements.append(Image(str(branding.logo_path), width=0.8 * inch, height=0.8 * inch))
        elements.append(Spacer(1, 6))

    elements.append(Paragraph(template["title"], title_style))
    elements.append(Paragraph(context["company_name"], subtitle_style))
    elements.append(Spacer(1, 12))

    for key in ("identification", "parameters", "execution"):
        section = template["sections"][key]
        elements.append(Paragraph(section["heading"], heading_style))
        elements.append(_fields_table(render_fields(section["fields"], context)))
        elements.append(Spacer(1, 10))

    evaluation_section = template["sections"]["evaluation"]
    elements.append(Paragraph(evaluation_section["heading"], heading_style))
    eval_fields = render_fields(evaluation_section["fields"], context)
    eval_table = _fields_table(eval_fields)
    color = result_color_hex(data, template, branding)
    if color:
        eval_table.setStyle(TableStyle([("BACKGROUND", (1, 0), (1, 0), colors.HexColor(color))]))
    elements.append(eval_table)
    elements.append(Spacer(1, 10))

    samples_section = template["sections"]["samples_table"]
    elements.append(Paragraph(samples_section["heading"], heading_style))
    sampled = evenly_sampled(data.samples, samples_section["max_rows"])
    sample_rows = [
        [s.timestamp, str(s.step_index), f"{s.voltage_measured:.3f}", f"{s.current_measured:.3f}"]
        for s in sampled
    ]
    elements.append(_data_table(samples_section["columns"], sample_rows, branding))
    elements.append(Spacer(1, 10))

    events_section = template["sections"]["events_table"]
    elements.append(Paragraph(events_section["heading"], heading_style))
    event_rows = [[e.timestamp or "", e.level, e.source, e.message] for e in data.events]
    elements.append(_data_table(events_section["columns"], event_rows, branding))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(template["footer"].format(**context), footer_style))

    doc.build(elements)
    return output_path
