"""Relatório FCT em Excel (.xlsx) via openpyxl, layout vindo de `report_template.yaml`.

Diferente do Word/PDF (documentos de leitura), a planilha é uma FERRAMENTA DE
ANÁLISE. Por isso:

- as amostras vão COMPLETAS (sem subamostrar) numa aba própria e como NÚMEROS
  reais (não texto), com timestamps reais — dá para filtrar, ordenar e plotar;
- formatação condicional realça em vermelho as leituras fora da faixa de
  referência (tensão min/máx; corrente acima do limite) — informativo, nunca
  veredito automático;
- um gráfico nativo (editável) de tensão/corrente acompanha o resumo;
- abas separadas: Resumo, Amostras, Eventos.

A cor do resultado avaliado (verde/vermelho/amarelo) realça só a célula do
veredito que o operador já registrou.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.drawing.image import Image as XlImage
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from config import BrandingConfig
from reports.report_data import ReportData
from reports.template_engine import (
    build_context,
    load_template,
    render_fields,
    resolve_output_path,
    result_color_hex,
    step_stats_rows,
)

_LABEL_COL_WIDTH = 32
_VALUE_COL_WIDTH = 48


def _hex_fill(hex_color: str) -> PatternFill:
    h = hex_color.lstrip("#")
    return PatternFill(start_color=h, end_color=h, fill_type="solid")


def _write_heading(ws: Worksheet, row: int, text: str, branding: BrandingConfig, span: int = 2) -> int:
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(bold=True, color=branding.color_text_on_navy.lstrip("#"), size=12)
    cell.fill = _hex_fill(branding.color_secondary_navy)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    return row + 1


def _write_fields(ws: Worksheet, row: int, fields: list[tuple[str, str]]) -> int:
    for label, value in fields:
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=value)
        row += 1
    return row + 1


def _write_table(ws: Worksheet, row: int, columns: list[str], rows: list[list], branding: BrandingConfig) -> int:
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


def _parse_timestamp(ts: str | None):
    """Devolve datetime real quando possível (para o Excel tratar como data)."""
    if not ts:
        return ts
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(ts, fmt)
        except (ValueError, TypeError):
            pass
    return ts


def _build_summary_sheet(ws: Worksheet, data: ReportData, branding: BrandingConfig, template: dict, context: dict) -> None:
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
    ws.cell(row=row, column=1, value=context["company_name"]).font = Font(italic=True, size=11)
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

    stats_section = template["sections"]["step_stats_table"]
    stats_rows = step_stats_rows(data)
    if stats_rows:
        row = _write_heading(ws, row, stats_section["heading"], branding, span=len(stats_section["columns"]))
        # Estatísticas como números reais (não as strings formatadas do Word/PDF).
        numeric_rows = [
            [
                st.step_index + 1,
                st.sample_count,
                round(st.voltage_mean, 3),
                round(st.voltage_std, 3),
                round(st.voltage_min, 3),
                round(st.voltage_max, 3),
                round(st.current_mean, 3),
                round(st.current_min, 3),
                round(st.current_max, 3),
                st.voltage_out_of_range,
                st.current_over_limit,
            ]
            for st in data.step_stats
        ]
        stats_cols = [
            "Ciclo", "Amostras", "Tensão méd. (V)", "Tensão desv. (V)",
            "Tensão mín (V)", "Tensão máx (V)", "Corrente méd. (A)",
            "Corrente mín (A)", "Corrente máx (A)", "V fora da faixa", "I acima do limite",
        ]
        _write_table(ws, row, stats_cols, numeric_rows, branding)


def _build_samples_sheet(ws: Worksheet, data: ReportData, branding: BrandingConfig, context: dict) -> int:
    """Amostras completas como números; retorna a última linha de dados."""
    columns = ["Timestamp", "Passo", "Tensão (V)", "Corrente (A)"]
    for col_idx, header in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True, color=branding.color_text_on_navy.lstrip("#"))
        cell.fill = _hex_fill(branding.color_primary_navy)

    for i, s in enumerate(data.samples, start=2):
        ts_cell = ws.cell(row=i, column=1, value=_parse_timestamp(s.timestamp))
        if isinstance(ts_cell.value, dt.datetime):
            ts_cell.number_format = "yyyy-mm-dd hh:mm:ss.000"
        ws.cell(row=i, column=2, value=s.step_index)
        ws.cell(row=i, column=3, value=round(s.voltage_measured, 4))
        ws.cell(row=i, column=4, value=round(s.current_measured, 4))

    last_row = len(data.samples) + 1
    ws.column_dimensions["A"].width = 24
    for col in ("B", "C", "D"):
        ws.column_dimensions[col].width = 14
    ws.freeze_panes = "A2"
    if last_row >= 1:
        ws.auto_filter.ref = f"A1:D{max(last_row, 1)}"

    # Formatação condicional: realça leituras fora da faixa de referência.
    if data.samples:
        cfg = data.config_snapshot
        red = _hex_fill(branding.color_fail)
        v_lo, v_hi = cfg.get("voltage_min"), cfg.get("voltage_max")
        i_hi = cfg.get("current_max")
        v_range = f"C2:C{last_row}"
        i_range = f"D2:D{last_row}"
        if v_lo is not None:
            ws.conditional_formatting.add(v_range, CellIsRule(operator="lessThan", formula=[str(v_lo)], fill=red))
        if v_hi is not None:
            ws.conditional_formatting.add(v_range, CellIsRule(operator="greaterThan", formula=[str(v_hi)], fill=red))
        if i_hi is not None:
            ws.conditional_formatting.add(i_range, CellIsRule(operator="greaterThan", formula=[str(i_hi)], fill=red))
    return last_row


def _add_chart(ws_summary: Worksheet, ws_samples: Worksheet, last_row: int) -> None:
    if last_row < 2:
        return
    chart = LineChart()
    chart.title = "Tensão e corrente × amostra"
    chart.height = 8
    chart.width = 18
    data_ref = Reference(ws_samples, min_col=3, max_col=4, min_row=1, max_row=last_row)
    cats_ref = Reference(ws_samples, min_col=1, min_row=2, max_row=last_row)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    ws_summary.add_chart(chart, "D2")


def generate_excel_report(
    data: ReportData, branding: BrandingConfig, output_dir: Path, base_name: str | None = None
) -> Path:
    template = load_template()
    context = build_context(data, branding)

    wb = Workbook()
    ws_summary = wb.active
    ws_summary.title = "Resumo"
    ws_samples = wb.create_sheet("Amostras")
    ws_events = wb.create_sheet("Eventos")

    _build_summary_sheet(ws_summary, data, branding, template, context)
    last_row = _build_samples_sheet(ws_samples, data, branding, context)
    _add_chart(ws_summary, ws_samples, last_row)

    events_columns = template["sections"]["events_table"]["columns"]
    event_rows = [[e.timestamp or "", e.level, e.source, e.message] for e in data.events]
    _write_table(ws_events, 1, events_columns, event_rows, branding)
    ws_events.column_dimensions["A"].width = 24
    ws_events.column_dimensions["D"].width = 60
    ws_events.freeze_panes = "A2"

    footer_cell = ws_summary.cell(row=ws_summary.max_row + 2, column=1, value=template["footer"].format(**context))
    footer_cell.font = Font(italic=True, size=9)
    footer_cell.alignment = Alignment(horizontal="left")

    output_path = resolve_output_path(data, output_dir, "xlsx", base_name)
    wb.save(output_path)
    return output_path
