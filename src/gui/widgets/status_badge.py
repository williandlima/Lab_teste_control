"""Badges de status que replicam os anunciadores físicos da E363x
(Rmt, Adrs, CV, CC, OVP, OCP, OFF) — seção 11.1.

Limitação assumida e sinalizada: CV/CC/OVP-tripped/OCP-tripped exigiriam
ler os registradores STATus:QUEStionable/STATus:OPERation, que NÃO estavam
no subset de comandos validado contra o manual oficial (seção 9.3). Para
não inventar mnemônicos, este widget só reflete estados que o driver
realmente sabe com certeza: REMOTO (após SYSTem:REMote), SAÍDA (ON/OFF) e
PROTEÇÃO ARMADA (configurada, não necessariamente disparada). Os badges de
CV/CC ficam disponíveis na UI já com o layout correto, em estado "N/D",
para quando os registradores forem validados e plugados em uma iteração
futura.
"""
from __future__ import annotations

from PySide6 import QtWidgets


class StatusBadge(QtWidgets.QLabel):
    _COLOR_ACTIVE = "#2ECC71"
    _COLOR_INACTIVE = "#5A5F66"
    _COLOR_UNKNOWN = "#8A9099"

    def __init__(self, label: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setProperty("statusBadge", "true")
        self._label = label
        self.set_unknown()

    def set_active(self, active: bool) -> None:
        color = self._COLOR_ACTIVE if active else self._COLOR_INACTIVE
        self.setStyleSheet(f"background-color: {color}; color: #0A1F44;")
        self.setText(self._label)

    def set_unknown(self) -> None:
        self.setStyleSheet(f"background-color: {self._COLOR_UNKNOWN}; color: #0A1F44;")
        self.setText(f"{self._label} (N/D)")
