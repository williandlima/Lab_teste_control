"""Carrega `templates/report_template.yaml` e monta o contexto de substituição.

Compartilhado pelos três geradores (Excel/Word/PDF) para que nenhum deles
duplique a lógica de "como virar `ReportData` + `BrandingConfig` em texto
pronto para impressão" — só o layout (onde cada campo aparece) é específico
de cada formato.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config import BrandingConfig
from database.models import EvaluationResult
from reports.report_data import ReportData

_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "report_template.yaml"

_RESULT_LABELS = {
    EvaluationResult.APPROVED: "Aprovado",
    EvaluationResult.REJECTED: "Reprovado",
    EvaluationResult.OBSERVATION: "Observação",
}


def load_template(path: Path | None = None) -> dict[str, Any]:
    with (path or _TEMPLATE_PATH).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fmt(value: float | None, decimals: int = 3) -> str:
    return f"{value:.{decimals}f}" if value is not None else "—"


def build_context(data: ReportData, branding: BrandingConfig) -> dict[str, str]:
    """Monta o dicionário usado pelos placeholders `{campo}` do template."""
    config = data.config_snapshot
    evaluation = data.evaluation

    context = {
        "company_name": branding.company_name,
        "session_id": str(data.session.id),
        "board_code": data.board.code,
        "board_part_number": data.board.part_number,
        "board_revision": data.board.revision,
        "serial_number": data.session.serial_number,
        "production_order": data.session.production_order or "—",
        "operator_name": data.operator.name,
        "started_at": data.session.started_at or "—",
        "finished_at": data.session.finished_at or "—",
        "nominal_voltage": _fmt(config.get("nominal_voltage")),
        "voltage_min": _fmt(config.get("voltage_min")),
        "voltage_max": _fmt(config.get("voltage_max")),
        "current_max": _fmt(config.get("current_max")),
        "test_duration_s": _fmt(config.get("test_duration_s"), decimals=1),
        "session_status": data.session.status.value,
        "sample_count": str(len(data.samples)),
        "voltage_min_observed": _fmt(data.voltage_min_observed),
        "voltage_max_observed": _fmt(data.voltage_max_observed),
        "current_min_observed": _fmt(data.current_min_observed),
        "current_max_observed": _fmt(data.current_max_observed),
        "evaluation_result": _RESULT_LABELS.get(evaluation.result, "—") if evaluation else "Pendente",
        "evaluation_operator_name": data.operator.name if evaluation else "—",
        "evaluated_at": (evaluation.evaluated_at or "—") if evaluation else "—",
        "evaluation_comment": (evaluation.comment or "—") if evaluation else "—",
    }
    return context


def render_fields(fields: list[list[str]], context: dict[str, str]) -> list[tuple[str, str]]:
    """Resolve os pares [rótulo, "{placeholder}"] de uma seção do template."""
    return [(label, value_template.format(**context)) for label, value_template in fields]


def result_color_hex(data: ReportData, template: dict[str, Any], branding: BrandingConfig) -> str | None:
    """Cor semântica (pass/fail/warning) do resultado avaliado, ou None se pendente."""
    if data.evaluation is None:
        return None
    color_attr = template["result_colors"].get(data.evaluation.result.value)
    return getattr(branding, color_attr) if color_attr else None


def report_filename(data: ReportData, extension: str) -> str:
    safe_code = "".join(c if c.isalnum() else "-" for c in data.board.code)
    safe_serial = "".join(c if c.isalnum() else "-" for c in data.session.serial_number)
    return f"FCT_{safe_code}_{safe_serial}_{data.session.id}.{extension}"


def evenly_sampled(items: list[Any], max_items: int) -> list[Any]:
    """Subamostra uniforme para tabelas de relatório (granularidade completa fica no banco)."""
    if max_items <= 0 or len(items) <= max_items:
        return items
    step = len(items) / max_items
    return [items[int(i * step)] for i in range(max_items)]
