"""Testa reports/branding_assets.py: a logo não pode ser esticada numa caixa
quadrada arbitrária nos exports (PDF/Excel já fizeram isso antes -- ver
pdf_report.py/excel_report.py, que agora chamam logo_aspect_height())."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from reports.branding_assets import logo_aspect_height

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_LOGO = _REPO_ROOT / "assets" / "branding" / "avibras_aeroco_logo.png"


def test_logo_aspect_height_matches_real_asset_aspect_ratio() -> None:
    with Image.open(_REAL_LOGO) as img:
        width_px, height_px = img.size
    expected_ratio = height_px / width_px  # logo real é landscape (~0.47)

    height = logo_aspect_height(_REAL_LOGO, target_width=100.0)

    assert height == pytest.approx(100.0 * expected_ratio, rel=1e-6)


def test_logo_aspect_height_is_unit_agnostic(tmp_path: Path) -> None:
    """Funciona igual em polegadas (PDF) ou pixels (Excel) -- só precisa que
    quem chama use a mesma unidade para largura e altura."""
    landscape = Image.new("RGBA", (200, 100))  # 2:1 landscape sintético
    path = tmp_path / "landscape.png"
    landscape.save(path)

    assert logo_aspect_height(path, target_width=1.0) == pytest.approx(0.5, rel=1e-6)
    assert logo_aspect_height(path, target_width=90.0) == pytest.approx(45.0, rel=1e-6)
