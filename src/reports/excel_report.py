"""Relatório FCT em Excel (.xlsx) via openpyxl, layout vindo de `report_template.yaml`.

Usa a identidade visual da Avibras Aeroco (`BrandingConfig`): cabeçalhos em
azul-marinho, destaques em laranja, e a cor do resultado avaliado (verde/
vermelho/amarelo) só na célula do veredito — nunca como decisão automática,
apenas para realçar visualmente o que o operador já registrou.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

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

_LABEL_COL_WIDTH = 32
_VALUE_COL_WIDTH = 48


def _hex_fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color.lstrip("#"), end_color=hex_color.lstrip("#"), fill_type="solid")


def _write_heading(ws: Worksheet, row: int, text: str, branding: BrandingConfig) -> int:
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(bold=True, color=branding.color_text_on_navy.lstrip("#"), size=12)
    cell.fill = _hex_fill(branding.color_secondary_navy)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    return row + 1


def _write_fields(ws: Worksheet, row: int, fields: list[tuple[str, str]]) -> int:
    for label, value in fields:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=value)
        row += 1
    return row + 1


def _write_table(ws: Worksheet, row: int, columns: list[str], rows: list[list[str]], branding: BrandingConfig) -> int:
    for col_idx, header in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=col_idx, value=header)
        cell.font = Font(bold=True, color=branding.color_text_on_navy.lstrip("#"))
        cell.fill = _hex_fill(branding.color_primary_navy)
    row += 1
    for data_row in rows:
        for col_idx, value in enumerate(data_row, start=1):
            ws.cell(row=row, column=col_idx, value=value)
        row += 1
    return row + 1


def generate_excel_report(data: ReportData, branding: BrandingConfig, output_dir: Path) -> Path:
    template = load_template()
    context = build_context(data, branding)

    wb = Workbook()
    ws = wb.active
    ws.title = "FCT Report"
    ws.column_dimensions["A"].width = _LABEL_COL_WIDTH
    ws.column_dimensions["B"].width = _VALUE_COL_WIDTH

    row = 1
    if branding.logo_path.exists():
        img = XlImage(str(branding.logo_path))
        img.height = 60
        img.width = 60
        ws.add_image(img, "A1")
        row = 5

    title_cell = ws.cell(row=row, column=1, value=template["title"])
    title_cell.font = Font(bold=True, size=16, color=branding.color_primary_navy.lstrip("#"))
    row += 1
    subtitle_cell = ws.cell(row=row, column=1, value=context["company_name"])
    subtitle_cell.font = Font(italic=True, size=11)
    row += 2

    for key in ("identification", "parameters", "execution"):
        section = template["sections"][key]
        row = _write_heading(ws, row, section["heading"], branding)
        row = _write_fields(ws, row, render_fields(section["fields"], context))

    evaluation_section = template["sections"]["evaluation"]
    row = _write_heading(ws, row, evaluation_section["heading"], branding)
    eval_fields = render_fields(evaluation_section["fields"], context)
    result_row = row
    row = _write_fields(ws, row, eval_fields)
    color = result_color_hex(data, template, branding)
    if color:
        ws.cell(row=result_row, column=2).fill = _hex_fill(color)

    samples_section = template["sections"]["samples_table"]
    row = _write_heading(ws, row, samples_section["heading"], branding)
    sampled = evenly_sampled(data.samples, samples_section["max_rows"])
    sample_rows = [
        [s.timestamp, str(s.step_index), f"{s.voltage_measured:.3f}", f"{s.current_measured:.3f}"]
        for s in sampled
    ]
    row = _write_table(ws, row, samples_section["columns"], sample_rows, branding)

    events_section = template["sections"]["events_table"]
    row = _write_heading(ws, row, events_section["heading"], branding)
    event_rows = [[e.timestamp or "", e.level, e.source, e.message] for e in data.events]
    row = _write_table(ws, row, events_section["columns"], event_rows, branding)

    footer_cell = ws.cell(row=row, column=1, value=template["footer"].format(**context))
    footer_cell.font = Font(italic=True, size=9)
    footer_cell.alignment = Alignment(horizontal="left")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / report_filename(data, "xlsx")
    wb.save(output_path)
    return output_path
