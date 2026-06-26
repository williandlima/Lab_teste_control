"""Cabeçalho persistente: marca (logo) + conexão com a fonte + passo atual.

Reúne em um único widget reutilizável duas necessidades levantadas na revisão:
1. a identidade visual da empresa (a logo existia em assets/ mas não aparecia
   em nenhuma tela);
2. a escolha manual da porta COM pelo operador e um "Testar conexão" que
   diagnostica cabo/parâmetros ANTES de aplicar tensão em qualquer placa.

Fica sempre visível acima do QStackedWidget, então o operador pode reconectar
ou trocar de porta em qualquer etapa do fluxo sem perder o contexto.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from config import BrandingConfig
from drivers.serial_driver import list_available_ports
from gui.widgets.status_badge import StatusBadge

_AUTO_LABEL = "Automático (config / VID-PID)"


class HeaderBar(QtWidgets.QWidget):
    # Emite a porta escolhida ("" = automático) quando o operador pede o teste.
    test_connection_requested = QtCore.Signal(str)

    def __init__(self, branding: BrandingConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBar")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.logo_label = QtWidgets.QLabel()
        self._load_logo(branding)
        layout.addWidget(self.logo_label)

        self.step_label = QtWidgets.QLabel("")
        self.step_label.setObjectName("headerStep")
        layout.addWidget(self.step_label)

        layout.addStretch()

        layout.addWidget(QtWidgets.QLabel("Porta da fonte:"))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setMinimumWidth(220)
        layout.addWidget(self.port_combo)

        self.refresh_button = QtWidgets.QPushButton("Atualizar")
        self.refresh_button.clicked.connect(self.refresh_ports)
        layout.addWidget(self.refresh_button)

        self.test_button = QtWidgets.QPushButton("Testar conexão")
        self.test_button.clicked.connect(self._emit_test_request)
        layout.addWidget(self.test_button)

        # Modo simulação: roda o ensaio com uma fonte virtual, sem hardware.
        self.simulate_check = QtWidgets.QCheckBox("Simulação")
        self.simulate_check.setToolTip(
            "Marque para rodar o ensaio com uma fonte SIMULADA (sem hardware conectado)."
        )
        layout.addWidget(self.simulate_check)

        self.connection_badge = StatusBadge("FONTE")
        layout.addWidget(self.connection_badge)

        self.refresh_ports()

    # -- logo ---------------------------------------------------------------

    def _load_logo(self, branding: BrandingConfig) -> None:
        if branding.logo_path.exists():
            pixmap = QtGui.QPixmap(str(branding.logo_path))
            if not pixmap.isNull():
                self.logo_label.setPixmap(
                    pixmap.scaledToHeight(44, QtCore.Qt.TransformationMode.SmoothTransformation)
                )
                self.logo_label.setToolTip(branding.company_name)
                return
        # Fallback textual se o arquivo da logo sumir: a marca nunca fica em branco.
        self.logo_label.setText(branding.company_name)
        self.logo_label.setStyleSheet("font-weight: bold; font-size: 14pt;")

    # -- portas COM ---------------------------------------------------------

    def refresh_ports(self) -> None:
        """Recarrega a lista de portas disponíveis, preservando a seleção atual."""
        current = self.selected_port()
        self.port_combo.clear()
        self.port_combo.addItem(_AUTO_LABEL, userData="")
        for port in list_available_ports():
            label = f"{port.device} — {port.description}" if port.description else port.device
            self.port_combo.addItem(label, userData=port.device)
        index = self.port_combo.findData(current)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)

    def selected_port(self) -> str:
        """Porta escolhida pelo operador, ou "" para resolução automática."""
        return self.port_combo.currentData() or ""

    def simulation_enabled(self) -> bool:
        """True se o operador marcou o modo simulação (fonte virtual)."""
        return self.simulate_check.isChecked()

    def set_simulation_enabled(self, enabled: bool) -> None:
        self.simulate_check.setChecked(enabled)

    # -- estado de conexão / passo -----------------------------------------

    def set_step(self, text: str) -> None:
        self.step_label.setText(f"  ·  {text}" if text else "")

    def set_connection_state(self, connected: bool, tooltip: str = "") -> None:
        self.connection_badge.set_active(connected)
        self.connection_badge.setToolTip(tooltip)

    def set_connection_unknown(self, tooltip: str = "") -> None:
        self.connection_badge.set_unknown()
        self.connection_badge.setToolTip(tooltip)

    def set_testing(self, testing: bool) -> None:
        """Desabilita os controles enquanto a sonda roda, evitando reentrância."""
        self.test_button.setEnabled(not testing)
        self.refresh_button.setEnabled(not testing)
        self.port_combo.setEnabled(not testing)
        self.test_button.setText("Testando…" if testing else "Testar conexão")

    def _emit_test_request(self) -> None:
        self.test_connection_requested.emit(self.selected_port())
