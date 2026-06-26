"""Indicador visual de etapas (stepper) do fluxo do ensaio.

Substitui o antigo rótulo textual ("· Parâmetros") por uma trilha
Cadastro → Parâmetros → Ensaio → Avaliação, com a etapa atual destacada,
as concluídas em destaque de marca e as futuras esmaecidas. A aparência é
controlada por propriedades dinâmicas (``stepState``) resolvidas no
theme.qss, mantendo as cores fora do código Python.
"""
from __future__ import annotations

from PySide6 import QtWidgets


class StepIndicator(QtWidgets.QWidget):
    """Trilha horizontal de etapas; ``set_current`` realça a etapa ativa."""

    def __init__(self, steps: list[str], parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stepIndicator")
        self._current = 0

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self._step_labels: list[QtWidgets.QLabel] = []
        for index, name in enumerate(steps):
            if index > 0:
                separator = QtWidgets.QLabel("›")
                separator.setObjectName("stepSeparator")
                layout.addWidget(separator)
            label = QtWidgets.QLabel(f"{index + 1}. {name}")
            self._step_labels.append(label)
            layout.addWidget(label)
        layout.addStretch()

        self.set_current(0)

    def set_current(self, index: int) -> None:
        self._current = index
        for i, label in enumerate(self._step_labels):
            if i < index:
                state = "done"
            elif i == index:
                state = "current"
            else:
                state = "todo"
            label.setProperty("stepState", state)
            # Repolir para o QSS reagir à mudança de propriedade dinâmica.
            label.style().unpolish(label)
            label.style().polish(label)
