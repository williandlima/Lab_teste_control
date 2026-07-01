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

# 1.5x a resolução original (960x420, ~150 DPI num embed de 6,4"): nítido o
# bastante para impressão/zoom sem pesar o arquivo.
_W, _H = 1440, 630
_M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 105, 105, 69, 78
_MAX_POINTS = 600
_FONT_SIZE = 16

_COLOR_VOLTAGE = "#FF7A29"   # laranja — tensão (preset)
_COLOR_CURRENT = "#1F9E91"   # teal — corrente (grandeza primária)
_COLOR_V_REF   = "#FF7A29"   # limites de tensão: laranja tracejado
_COLOR_I_LIMIT = "#E74C3C"   # limite de corrente: vermelho tracejado (faixa crítica)
_COLOR_AXIS = "#444444"
_COLOR_GRID = "#DDDDDD"
_COLOR_TEXT = "#222222"

_LINE_W_CURRENT = 3    # corrente: linha grossa (grandeza primária)
_LINE_W_VOLTAGE = 2    # tensão: linha padrão

_FONT_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"


def _load_font(size: int) -> ImageFont.ImageFont:
    """Fonte TrueType legível para o PNG do gráfico.

    `ImageFont.load_default()` é um bitmap minúsculo sem antialiasing — destoa
    do resto do documento Word/PDF, e não cobre "ã"/"×" (caixas de glifo
    ausente: "Tensão" virava "Tens□o"). DejaVu Sans tem cobertura Unicode
    completa e vem embutida em `assets/fonts/` (mesmo padrão do logo em
    `assets/branding/`) para não depender de fonte instalada no SO do
    operador (Windows de chão de fábrica, sem garantia de DejaVu). Cai para
    o bitmap padrão só se o arquivo sumir do pacote.
    """
    try:
        return ImageFont.truetype(str(_FONT_PATH), size)
    except Exception:
        return ImageFont.load_default()


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

    # Escala de corrente: sempre parte do 0 e acompanha a corrente REAL
    # observada — não o limite de proteção configurado (`current_max`), que
    # costuma ser bem maior que a corrente do DUT. Usar o limite como piso da
    # escala (como antes) espremia a curva real perto de zero — o mesmo
    # defeito já corrigido no gráfico ao vivo (`gui/widgets/live_chart.py`).
    i_observed_max = max(amps)
    i_scale_max = max(i_observed_max * 1.3, 0.05)
    i_lo = 0.0

    x_lo, x_hi = (xs[0], xs[-1]) if xs[-1] > xs[0] else (0.0, 1.0)

    img = Image.new("RGB", (_W, _H), "white")
    draw = ImageDraw.Draw(img)
    font = _load_font(_FONT_SIZE)
    title_font = _load_font(_FONT_SIZE + 4)

    plot_l, plot_r = _M_LEFT, _W - _M_RIGHT
    plot_t, plot_b = _M_TOP, _H - _M_BOTTOM

    def px(x: float) -> float:
        return plot_l + (x - x_lo) / (x_hi - x_lo) * (plot_r - plot_l)

    def py_v(v: float) -> float:
        return plot_b - (v - v_lo) / (v_hi - v_lo) * (plot_b - plot_t)

    def py_i(a: float) -> float:
        return plot_b - (a - i_lo) / (i_scale_max - i_lo) * (plot_b - plot_t)

    # Título — corrente primeiro, refletindo a hierarquia do ensaio.
    draw.text((plot_l, 14), "Corrente e Tensão × Tempo", fill=_COLOR_TEXT, font=title_font)

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
    # Só desenha se estiver dentro da área visível: como a escala agora segue
    # a corrente observada (não mais o limite, ver acima), o limite de
    # proteção fica tipicamente bem acima do topo do gráfico — desenhar fora
    # da moldura poluiria o título/legenda com um traço sem contexto.
    if i_hi_ref is not None and i_lo <= i_hi_ref <= i_scale_max:
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
    # Largura calculada em vez de offsets fixos: com fonte TrueType (variável,
    # diferente da bitmap monoespaçada anterior) offsets fixos faziam os dois
    # rótulos se sobreporem ("Corrente (A" colidindo com o quadrado laranja).
    legend_gap = 20
    corrente_label, tensao_label = "■ Corrente (A)", "■ Tensão (V)"
    tensao_x = plot_r - draw.textlength(tensao_label, font=font)
    corrente_x = tensao_x - legend_gap - draw.textlength(corrente_label, font=font)
    draw.text((corrente_x, 14), corrente_label, fill=_COLOR_CURRENT, font=font)
    draw.text((tensao_x, 14), tensao_label, fill=_COLOR_VOLTAGE, font=font)

    output_path = Path(output_path)
    img.save(output_path, "PNG")
    return output_path
