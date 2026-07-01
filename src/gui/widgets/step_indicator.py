"""Indicador visual de etapas (stepper) do fluxo do ensaio.

Implementado com QPainter: círculos numerados conectados por linha, checkmark
nos passos concluídos e label abaixo de cada círculo. Não depende de
polimento QSS para os estados — toda a lógica visual está no paintEvent.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class StepIndicator(QtWidgets.QWidget):
    """Trilha horizontal pintada de etapas; ``set_current`` realça a etapa ativa."""

    _R = 13          # raio base do círculo
    _R_CURRENT = 15  # raio do passo ativo (levemente maior)
    _TOP_PAD = 7     # espaço acima do centro do círculo
    _LABEL_GAP = 5   # espaço entre borda inferior do círculo e o texto

    _C_DONE    = QtGui.QColor("#FF7A29")
    _C_CURRENT = QtGui.QColor("#FF7A29")
    _C_TODO    = QtGui.QColor("#5A5F66")
    _C_LINE    = QtGui.QColor("#3A4F7A")
    _C_NAVY    = QtGui.QColor("#0A1F44")

    def __init__(self, steps: list[str], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepIndicator")
        self._steps = steps
        self._current = 0
        # Altura: TOP_PAD + diâmetro_atual + gap + altura_rótulo + bottom_pad
        self.setMinimumHeight(self._TOP_PAD + self._R_CURRENT * 2 + self._LABEL_GAP + 14 + 6)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_current(self, index: int) -> None:
        self._current = index
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        # Pinta o fundo definido pelo QSS (#stepIndicator).
        opt = QtWidgets.QStyleOption()
        opt.initFrom(self)
        p = QtGui.QPainter(self)
        self.style().drawPrimitive(
            QtWidgets.QStyle.PrimitiveElement.PE_Widget, opt, p, self
        )
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        n = len(self._steps)
        if n == 0:
            return

        W = self.width()
        cy = self._TOP_PAD + self._R_CURRENT  # centro Y dos círculos

        step_w = W / n
        centers = [int(step_w * (i + 0.5)) for i in range(n)]

        # Linhas conectoras
        p.setPen(QtGui.QPen(self._C_LINE, 2))
        for i in range(n - 1):
            p.drawLine(centers[i] + self._R, cy, centers[i + 1] - self._R, cy)

        for i, (cx, name) in enumerate(zip(centers, self._steps)):
            is_done = i < self._current
            is_cur  = i == self._current

            if is_done:
                self._draw_done(p, cx, cy, i + 1)
            elif is_cur:
                self._draw_current(p, cx, cy, i + 1)
            else:
                self._draw_todo(p, cx, cy, i + 1)

            self._draw_label(p, cx, cy, name, is_done, is_cur)

    def _draw_done(self, p: QtGui.QPainter, cx: int, cy: int, num: int) -> None:
        R = self._R
        p.setBrush(self._C_DONE)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(QtCore.QPoint(cx, cy), R, R)

        # Checkmark ✓
        pen = QtGui.QPen(self._C_NAVY, 2, QtCore.Qt.PenStyle.SolidLine)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        h = R * 0.45
        p.drawLine(
            QtCore.QPointF(cx - h, cy + 1),
            QtCore.QPointF(cx - h * 0.2, cy + h * 0.9),
        )
        p.drawLine(
            QtCore.QPointF(cx - h * 0.2, cy + h * 0.9),
            QtCore.QPointF(cx + h * 0.9, cy - h * 0.6),
        )

    def _draw_current(self, p: QtGui.QPainter, cx: int, cy: int, num: int) -> None:
        R = self._R_CURRENT
        p.setBrush(self._C_CURRENT)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(QtCore.QPoint(cx, cy), R, R)

        p.setPen(self._C_NAVY)
        fnt = QtGui.QFont("Segoe UI", 9, QtGui.QFont.Weight.Bold)
        p.setFont(fnt)
        p.drawText(
            QtCore.QRect(cx - R, cy - R, R * 2, R * 2),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            str(num),
        )

    def _draw_todo(self, p: QtGui.QPainter, cx: int, cy: int, num: int) -> None:
        R = self._R
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(self._C_TODO, 1.5))
        p.drawEllipse(QtCore.QPoint(cx, cy), R, R)

        p.setPen(self._C_TODO)
        fnt = QtGui.QFont("Segoe UI", 9)
        p.setFont(fnt)
        p.drawText(
            QtCore.QRect(cx - R, cy - R, R * 2, R * 2),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            str(num),
        )

    def _draw_label(
        self,
        p: QtGui.QPainter,
        cx: int,
        cy: int,
        name: str,
        is_done: bool,
        is_cur: bool,
    ) -> None:
        R = self._R_CURRENT if is_cur else self._R
        label_y = cy + R + self._LABEL_GAP
        rect = QtCore.QRect(cx - 52, label_y, 104, 16)

        if is_done:
            p.setPen(self._C_DONE)
            fnt = QtGui.QFont("Segoe UI", 8)
        elif is_cur:
            p.setPen(self._C_CURRENT)
            fnt = QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold)
        else:
            p.setPen(self._C_TODO)
            fnt = QtGui.QFont("Segoe UI", 8)

        p.setFont(fnt)
        p.drawText(rect, QtCore.Qt.AlignmentFlag.AlignHCenter, name)
