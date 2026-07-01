"""Relatório FCT em PDF via reportlab (platypus), layout vindo de `report_template.yaml`.

Mesma identidade visual e mesma regra dos outros dois formatos
(`excel_report.py`, `word_report.py`): o resultado avaliado pelo operador é
apenas realçado na cor semântica correspondente, nunca calculado aqui.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_PAGE_USABLE_WIDTH = A4[0] - 2 * inch  # margens padrão do SimpleDocTemplate: 1" de cada lado


class _NumberedCanvas(Canvas):
    """Canvas que grava 'Página X de Y' — reportlab só sabe o total de
    páginas depois de renderizar tudo, então guarda o estado de cada página
    e desenha o rodapé numa segunda passada em `save()`.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, total_pages: int) -> None:
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawRightString(
            A4[0] - 0.6 * inch, 0.4 * inch, f"Página {self._pageNumber} de {total_pages}"
        )

from config import BrandingConfig
from reports.chart import render_samples_chart
from reports.report_data import ReportData
from reports.template_engine import (
    build_context,
    evenly_sampled,
    load_template,
    render_fields,
    resolve_output_path,
    result_color_hex,
    step_stats_rows,
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


def _data_table(
    columns: list[str], rows: list[list[str]], branding: BrandingConfig, col_widths: list[float] | None = None
) -> Table:
    """Tabela com células em `Paragraph` (quebram linha) em vez de string pura.

    Descoberto ao inspecionar o PDF renderizado: strings simples NÃO quebram
    linha em `Table` do reportlab — só transbordam por cima da coluna vizinha
    sem erro nenhum. Com 10 colunas (tabela de estatísticas por ciclo) isso
    produzia texto sobreposto e ilegível. `colWidths` explícito (proporcional
    ao tamanho do cabeçalho quando não informado) garante que a tabela nunca
    ultrapassa a largura da página.
    """
    header_style = ParagraphStyle(
        "FctTableHeader", fontName="Helvetica-Bold", fontSize=8, leading=10,
        textColor=colors.HexColor(branding.color_text_on_navy),
    )
    cell_style = ParagraphStyle("FctTableCell", fontName="Helvetica", fontSize=8, leading=10)

    if col_widths is None:
        weights = [max(len(str(c)), 6) for c in columns]
        total_weight = sum(weights)
        col_widths = [_PAGE_USABLE_WIDTH * w / total_weight for w in weights]
        # Piso mínimo: com muitas colunas (ex. 10 na tabela de estatísticas),
        # a proporção pura deixa cabeçalhos curtos ("Ciclo", "Amostras") com
        # largura menor que uma letra — o texto quebra uma letra por linha.
        # Reescala proporcionalmente depois de aplicar o piso para não
        # ultrapassar a largura útil da página.
        min_width = 0.55 * inch
        col_widths = [max(w, min_width) for w in col_widths]
        total_width = sum(col_widths)
        if total_width > _PAGE_USABLE_WIDTH:
            scale = _PAGE_USABLE_WIDTH / total_width
            col_widths = [w * scale for w in col_widths]

    header_row = [Paragraph(str(h), header_style) for h in columns]
    body_rows = [[Paragraph(str(v), cell_style) for v in data_row] for data_row in rows]
    table = Table([header_row] + body_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(branding.color_primary_navy)),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def generate_pdf_report(
    data: ReportData, branding: BrandingConfig, output_dir: Path, base_name: str | None = None
) -> Path:
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

    output_path = resolve_output_path(data, output_dir, "pdf", base_name)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4)

    elements: list = []
    if branding.logo_path.exists():
        elements.append(Image(str(branding.logo_path), width=0.8 * inch, height=0.8 * inch))
        elements.append(Spacer(1, 6))

    elements.append(Paragraph(template["title"], title_style))
    elements.append(Paragraph(context["company_name"], subtitle_style))
    elements.append(Spacer(1, 12))

    for key in ("identification", "parameters", "execution", "traceability"):
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        chart_png = render_samples_chart(data, branding, Path(tmp_dir) / "chart.png")
        if chart_png is not None:
            chart_section = template["sections"]["chart"]
            elements.append(Paragraph(chart_section["heading"], heading_style))
            elements.append(Image(str(chart_png), width=6.4 * inch, height=2.8 * inch))
            elements.append(Spacer(1, 10))

        stats_rows = step_stats_rows(data)
        if stats_rows:
            stats_section = template["sections"]["step_stats_table"]
            elements.append(Paragraph(stats_section["heading"], heading_style))
            elements.append(_data_table(stats_section["columns"], stats_rows, branding))
            elements.append(Spacer(1, 10))

        samples_section = template["sections"]["samples_table"]
        elements.append(Paragraph(samples_section["heading"], heading_style))
        sampled = evenly_sampled(data.samples, samples_section["max_rows"])
        sample_rows = [
            [s.timestamp, str(s.step_index + 1), f"{s.current_measured:.3f}", f"{s.voltage_measured:.3f}"]
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

        # build() lê a imagem do disco; precisa ocorrer com o tmp_dir ainda aberto.
        doc.build(elements, canvasmaker=_NumberedCanvas)
    return output_path
