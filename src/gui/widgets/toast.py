"""Aviso não-bloqueante (toast) sobreposto à janela.

Substitui os ``QMessageBox.information`` de baixa criticidade — que
interrompiam o fluxo e exigiam um clique em "OK" — por uma faixa discreta
que aparece sobre a janela e some sozinha. Modais ficam reservados para o
que realmente exige decisão (confirmar energização) ou erro (falha de
conexão/geração de relatório).

A cor da borda segue o nível (info/sucesso/aviso) via propriedade dinâmica
``toastLevel`` resolvida no theme.qss.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class Toast(QtWidgets.QLabel):
    """Faixa flutuante com auto-desaparecimento, ancorada ao rodapé do pai."""

    def __init__(self, parent: QtWidgets.QWidget, message: str, level: str, duration_ms: int) -> None:
        super().__init__(message, parent)
        self.setObjectName("toast")
        self.setProperty("toastLevel", level)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

        self._fade = QtCore.QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(300)
        self._fade.finished.connect(self._on_fade_finished)

        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

        QtCore.QTimer.singleShot(duration_ms, self._start_fade_out)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setMaximumWidth(int(parent.width() * 0.8))
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 32
        self.move(max(0, x), max(0, y))

    def _start_fade_out(self) -> None:
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._fade.endValue() == 0.0:
            self.deleteLater()


def show_toast(
    parent: QtWidgets.QWidget,
    message: str,
    level: str = "info",
    duration_ms: int = 3000,
) -> Toast:
    """Mostra um toast sobre ``parent``. level ∈ {info, success, warning}."""
    return Toast(parent, message, level, duration_ms)
