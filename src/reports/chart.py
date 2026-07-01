"""Gráfico estático tensão/corrente × tempo para os relatórios Word/PDF.

Renderizado com Pillow (sem matplotlib) para não acrescentar dependência
pesada e funcionar headless. O Excel usa gráfico nativo do openpyxl (ver
excel_report.py); aqui é só o PNG embutido no documento.

Hierarquia visual alinhada ao core do projeto:
- Corrente: linha GROSSA (2.5px), eixo Y direito em teal — é a grandeza
  primária que o operador está observando;
- Tensão: linha FINA (1.5px), eixo Y esquerdo em laranja — é o preset do
  procedimento, necessário mas não o foco;
- Limite de corrente (current_max): linha tracejada vermelha — faixa crítica;
- Referências de tensão (voltage_min/max): linhas tracejadas laranjas — guias
  de referência, não gatilho automático de reprovação.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import BrandingConfig
from reports.report_data import ReportData

_W, _H = 960, 420
_M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 70, 70, 46, 52
_MAX_POINTS = 600

_COLOR_VOLTAGE = "#FF7A29"   # laranja — tensão (preset)
_COLOR_CURRENT = "#1F9E91"   # teal — corrente (grandeza primária)
_COLOR_V_REF   = "#FF7A29"   # limites de tensão: laranja tracejado
_COLOR_I_LIMIT = "#E74C3C"   # limite de corrente: vermelho tracejado (faixa crítica)
_COLOR_AXIS = "#444444"
_COLOR_GRID = "#DDDDDD"
_COLOR_TEXT = "#222222"

_LINE_W_CURRENT = 3    # corrente: linha grossa (grandeza primária)
_LINE_W_VOLTAGE = 2    # tensão: linha padrão


def _parse_elapsed_seconds(timestamps: list[str]) -> list[float]:
    """Converte timestamps em segundos decorridos do início; cai para índice."""
    parsed: list[dt.datetime] = []
    for ts in timestamps:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed.append(dt.datetime.strptime(ts, fmt))
                break
            except (ValueError, TypeError):
                pass
        else:
            return [float(i) for i in range(len(timestamps))]
    start = parsed[0]
    return [(p - start).total_seconds() for p in parsed]


def _decimate(values: list, max_points: int) -> list:
    if len(values) <= max_points:
        return values
    step = len(values) / max_points
    return [values[int(i * step)] for i in range(max_points)]


def _nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if high <= low:
        high = low + 1.0
    return [low + (high - low) * i / count for i in range(count + 1)]


def render_samples_chart(data: ReportData, branding: BrandingConfig, output_path: Path) -> Path | None:
    """Gera o PNG do gráfico em `output_path`; retorna None se não há amostras."""
    if not data.samples:
        return None

    samples = _decimate(data.samples, _MAX_POINTS)
    xs = _parse_elapsed_seconds([s.timestamp for s in samples])
    volts = [s.voltage_measured for s in samples]
    amps = [s.current_measured for s in samples]

    cfg = data.config_snapshot
    v_lo_ref, v_hi_ref = cfg.get("voltage_min"), cfg.get("voltage_max")
    i_hi_ref = cfg.get("current_max")

    # Escala de tensão: ancorada nas referências, expandida para incluir observado.
    v_lo = min(volts + ([v_lo_ref] if v_lo_ref is not None else []))
    v_hi = max(volts + ([v_hi_ref] if v_hi_ref is not None else []))
    v_pad = (v_hi - v_lo) * 0.08 or 0.5
    v_lo, v_hi = v_lo - v_pad, v_hi + v_pad

    # Escala de corrente: sempre parte do 0, alcança o máximo observado + 10%
    # (ou o limite configurado, o que for maior).
    i_observed_max = max(amps)
    i_scale_max = max(i_observed_max, i_hi_ref if i_hi_ref is not None else 0.0) * 1.1 or 1.0
    i_lo = 0.0

    x_lo, x_hi = (xs[0], xs[-1]) if xs[-1] > xs[0] else (0.0, 1.0)

    img = Image.new("RGB", (_W, _H), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    plot_l, plot_r = _M_LEFT, _W - _M_RIGHT
    plot_t, plot_b = _M_TOP, _H - _M_BOTTOM

    def px(x: float) -> float:
        return plot_l + (x - x_lo) / (x_hi - x_lo) * (plot_r - plot_l)

    def py_v(v: float) -> float:
        return plot_b - (v - v_lo) / (v_hi - v_lo) * (plot_b - plot_t)

    def py_i(a: float) -> float:
        return plot_b - (a - i_lo) / (i_scale_max - i_lo) * (plot_b - plot_t)

    # Título — corrente primeiro, refletindo a hierarquia do ensaio.
    draw.text((plot_l, 14), "Corrente e Tensão × Tempo", fill=_COLOR_TEXT, font=font)

    # Grade horizontal + rótulos: tensão à esquerda (laranja), corrente à direita (teal).
    for v in _nice_ticks(v_lo, v_hi):
        y = py_v(v)
        draw.line([(plot_l, y), (plot_r, y)], fill=_COLOR_GRID)
        draw.text((4, y - 6), f"{v:.2f}", fill=_COLOR_VOLTAGE, font=font)
    for a in _nice_ticks(i_lo, i_scale_max):
        y = py_i(a)
        draw.text((plot_r + 6, y - 6), f"{a:.3f}", fill=_COLOR_CURRENT, font=font)

    # Rótulos do eixo X (tempo decorrido).
    for tick in _nice_ticks(x_lo, x_hi):
        x = px(tick)
        draw.line([(x, plot_b), (x, plot_b + 4)], fill=_COLOR_AXIS)
        draw.text((x - 10, plot_b + 8), f"{tick:.0f}s", fill=_COLOR_TEXT, font=font)

    # Linhas de referência de TENSÃO (laranja tracejado) — guias, não veredito.
    for ref in (v_lo_ref, v_hi_ref):
        if ref is None:
            continue
        y = py_v(ref)
        for seg in range(plot_l, plot_r, 12):
            draw.line([(seg, y), (min(seg + 6, plot_r), y)], fill=_COLOR_V_REF)

    # Linha de limite de CORRENTE (vermelho tracejado) — faixa crítica.
    if i_hi_ref is not None:
        y = py_i(i_hi_ref)
        for seg in range(plot_l, plot_r, 12):
            draw.line([(seg, y), (min(seg + 6, plot_r), y)], fill=_COLOR_I_LIMIT)

    # Moldura.
    draw.rectangle([plot_l, plot_t, plot_r, plot_b], outline=_COLOR_AXIS)

    # Séries: corrente primeiro (mais importante → ocorre por cima da tensão).
    v_points = [(px(xs[i]), py_v(volts[i])) for i in range(len(samples))]
    i_points = [(px(xs[i]), py_i(amps[i])) for i in range(len(samples))]
    if len(v_points) > 1:
        draw.line(v_points, fill=_COLOR_VOLTAGE, width=_LINE_W_VOLTAGE)
        draw.line(i_points, fill=_COLOR_CURRENT, width=_LINE_W_CURRENT)

    # Legenda — corrente primeiro, tensão depois, consistente com a hierarquia.
    draw.text((plot_r - 200, 14), "■ Corrente (A)", fill=_COLOR_CURRENT, font=font)
    draw.text((plot_r - 90,  14), "■ Tensão (V)",   fill=_COLOR_VOLTAGE, font=font)

    output_path = Path(output_path)
    img.save(output_path, "PNG")
    return output_path
