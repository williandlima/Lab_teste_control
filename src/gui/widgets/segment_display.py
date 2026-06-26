"""Painel de leitura estilo VFD da fonte Agilent/Keysight (seção 11.1).

Tenta carregar uma fonte de 7 segmentos (família DSEG, OFL — livre para uso
comercial) de `resources/fonts/`. Os arquivos .ttf não são gerados por
código e precisam ser copiados manualmente para essa pasta (baixe em
keshikan.net/fonts-e.html); na ausência deles, cai para uma fonte
monoespaçada do sistema com letter-spacing maior, para que a UI nunca quebre
por falta do asset.
"""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

_FONTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resources" / "fonts"

_segment_font_family: str | None = None
_fonts_loaded = False


def _load_segment_font_family() -> str | None:
    """Carrega a primeira fonte DSEG*.ttf encontrada; cacheia o resultado."""
    global _segment_font_family, _fonts_loaded
    if _fonts_loaded:
        return _segment_font_family

    _fonts_loaded = True
    if _FONTS_DIR.is_dir():
        for ttf_path in sorted(_FONTS_DIR.glob("*.ttf")):
            font_id = QtGui.QFontDatabase.addApplicationFont(str(ttf_path))
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _segment_font_family = families[0]
                break
    return _segment_font_family


class SegmentDisplay(QtWidgets.QLabel):
    """Mostra um valor numérico com unidade, estilo display de 7 segmentos."""

    def __init__(self, unit: str, decimals: int = 3, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._unit = unit
        self._decimals = decimals
        self._min_limit: float | None = None
        self._max_limit: float | None = None
        self.setObjectName("segmentDisplay")
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setMinimumHeight(64)

        family = _load_segment_font_family()
        font = QtGui.QFont(family if family else "Consolas")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPointSize(28)
        if family is None:
            font.setLetterSpacing(QtGui.QFont.PercentageSpacing, 110)
        self.setFont(font)

        self.set_value(0.0)

    def set_limits(self, minimum: float | None, maximum: float | None) -> None:
        """Define a faixa esperada; valores fora dela acendem o alarme visual."""
        self._min_limit = minimum
        self._max_limit = maximum

    def set_value(self, value: float) -> None:
        self.setText(f"{value:.{self._decimals}f} {self._unit}")
        self._apply_alarm(self._is_out_of_range(value))

    def _is_out_of_range(self, value: float) -> bool:
        if self._min_limit is not None and value < self._min_limit:
            return True
        if self._max_limit is not None and value > self._max_limit:
            return True
        return False

    def _apply_alarm(self, alarm: bool) -> None:
        # Só repolir quando o estado muda, para não retrabalhar o estilo a cada amostra.
        if self.property("alarm") == alarm:
            return
        self.setProperty("alarm", alarm)
        self.style().unpolish(self)
        self.style().polish(self)
