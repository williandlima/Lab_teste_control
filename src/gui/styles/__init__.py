"""Carregamento da folha de estilo única (theme.qss) com a paleta de marca.

Mantém os hex de cor fora do código Python: eles vêm de
`config/app_config.yaml` (branding) e são substituídos nos tokens
`{{TOKEN}}` do QSS antes de aplicar — trocar a marca não exige tocar em
nenhum .py.
"""
from __future__ import annotations

from pathlib import Path

from config import BrandingConfig

_THEME_PATH = Path(__file__).resolve().parent / "theme.qss"

_TOKEN_MAP = {
    "{{NAVY_PRIMARY}}": "color_primary_navy",
    "{{NAVY_SECONDARY}}": "color_secondary_navy",
    "{{ORANGE_ACCENT}}": "color_accent_orange",
    "{{ORANGE_ACCENT_HOVER}}": "color_accent_orange_hover",
    "{{TEXT_ON_NAVY}}": "color_text_on_navy",
    "{{COLOR_PASS}}": "color_pass",
    "{{COLOR_FAIL}}": "color_fail",
    "{{COLOR_WARNING}}": "color_warning",
}


def load_theme(branding: BrandingConfig) -> str:
    """Lê theme.qss e substitui os tokens de cor pelos valores de branding."""
    stylesheet = _THEME_PATH.read_text(encoding="utf-8")
    for token, attr_name in _TOKEN_MAP.items():
        stylesheet = stylesheet.replace(token, getattr(branding, attr_name))
    return stylesheet
