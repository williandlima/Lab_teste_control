"""Badges de status que replicam os anunciadores físicos da E363x
(Rmt, Adrs, CV, CC, OVP, OCP, OFF) — seção 11.1.

Implementado com QPainter: LED circular com gradiente radial (ativo = verde
brilhante com halo, inativo/desconhecido = cinza fosco) + texto à direita.
Preserva exatamente a mesma API pública do widget anterior (set_active /
set_unknown) sem quebrar nenhum chamador.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

_LED_R    = 5   # raio do LED em pixels
_PAD_H    = 10  # padding horizontal (lados)
_PAD_V    = 5   # padding vertical
_GAP      = 7   # gap entre LED e texto


class StatusBadge(QtWidgets.QWidget):
    """LED indicador de status — ponto luminoso circular + nome da grandeza."""

    def __init__(self, label: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self._label = label
        self._display_text = label
        self._led_on   = False
        self._unknown  = True
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.set_unknown()

    # ------------------------------------------------------------------ API

    def set_active(self, active: bool) -> None:
        self._led_on  = active
        self._unknown = False
        self._display_text = self._label
        self.update()

    def set_unknown(self) -> None:
        self._led_on  = False
        self._unknown = True
        self._display_text = f"{self._label} (N/D)"
        self.update()

    # ------------------------------------------------------------------ Qt

    def sizeHint(self) -> QtCore.QSize:
        fnt = QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold)
        fm  = QtGui.QFontMetrics(fnt)
        # Usar texto mais longo para reservar espaço fixo (evita resize ao mudar estado).
        worst = fm.horizontalAdvance(f"{self._label} (N/D)")
        w = _PAD_H + _LED_R * 2 + _GAP + worst + _PAD_H
        h = _PAD_V * 2 + max(_LED_R * 2, fm.height())
        return QtCore.QSize(w, h)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(0, 1, -1, -1)

        # Background rounded-pill
        if self._led_on:
            bg = QtGui.QColor("#162614")   # tinto verde-escuro
        elif self._unknown:
            bg = QtGui.QColor("#2A2F36")   # cinza neutro
        else:
            bg = QtGui.QColor("#1E2228")   # cinza apagado (inativo)

        p.setBrush(bg)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 10, 10)

        # Centro vertical
        cy = rect.height() // 2
        led_cx = _PAD_H + _LED_R

        # LED circle
        if self._led_on:
            grad = QtGui.QRadialGradient(
                QtCore.QPointF(led_cx - 1, cy - 2), float(_LED_R)
            )
            grad.setColorAt(0.0, QtGui.QColor("#BFFFD0"))   # centro brilhante
            grad.setColorAt(0.45, QtGui.QColor("#2ECC71"))  # verde médio
            grad.setColorAt(1.0, QtGui.QColor("#1A8A4A"))   # borda escura
            p.setBrush(grad)
            p.setPen(QtGui.QPen(QtGui.QColor("#2ECC71"), 0.8))
        else:
            color = QtGui.QColor("#4A5058") if self._unknown else QtGui.QColor("#2E3338")
            p.setBrush(color)
            p.setPen(QtCore.Qt.PenStyle.NoPen)

        p.drawEllipse(QtCore.QPointF(led_cx, cy), float(_LED_R), float(_LED_R))

        # Texto
        text_x = _PAD_H + _LED_R * 2 + _GAP
        fnt = QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold)
        p.setFont(fnt)
        fm = QtGui.QFontMetrics(fnt)
        text_h = fm.height()
        text_y = (rect.height() - text_h) // 2

        if self._led_on:
            p.setPen(QtGui.QColor("#C8F5D8"))
        elif self._unknown:
            p.setPen(QtGui.QColor("#7A828A"))
        else:
            p.setPen(QtGui.QColor("#4E5560"))

        p.drawText(
            QtCore.QRect(text_x, text_y, rect.width() - text_x - _PAD_H, text_h),
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            self._display_text,
        )
