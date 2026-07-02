"""Utilitário compartilhado para não distorcer a logo nos exports.

`pdf_report.py` e `excel_report.py` precisam da mesma conta (ler as
dimensões reais do arquivo, escalar mantendo a proporção) para embutir a
logo sem esticá-la numa caixa quadrada arbitrária -- ter essa lógica
duplicada nos dois arriscaria uma correção futura consertar um formato e
esquecer o outro (`word_report.py` já preserva a proporção nativamente:
`add_picture(..., width=...)` do python-docx calcula a altura sozinho).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def logo_aspect_height(logo_path: Path, target_width: float) -> float:
    """Altura proporcional para `target_width`, preservando o aspect ratio
    real do arquivo. Unidade agnóstica (polegadas, pixels...) -- width e
    height só precisam usar a MESMA unidade do lado de quem chama.
    """
    with Image.open(logo_path) as img:
        width_px, height_px = img.size
    return target_width * (height_px / width_px)
