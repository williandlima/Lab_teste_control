"""Diálogo de saída manual ("teste rápido"), espelhando o painel frontal da fonte.

Permite ao operador energizar a saída fora da sequência automática do ensaio —
útil para uma verificação rápida em bancada. É deliberadamente isolado do fluxo
Cadastro→Parâmetros→Monitoramento→Avaliação e tem três salvaguardas:

1. ``Ligar saída`` exige confirmação explícita (energizar uma placa fora da
   sequência controlada é o ponto de maior risco elétrico do app).
2. A saída é SEMPRE desligada ao fechar o diálogo (failsafe), mesmo em erro.

OVP/OCP NÃO são armados automaticamente aqui: um cálculo de margem (ex.: 10%
sobre o setpoint) já causou "SCPI error -222: Data out of range" em hardware
real (mesma causa-raiz corrigida no fluxo principal — ver state_machine.py).
Se o operador quiser proteção de hardware, deve armar OVP/OCP explicitamente
pela própria fonte ou pelo fluxo de ensaio completo, que pede o valor.

Todas as chamadas SCPI são bloqueantes e rodam fora da thread da GUI. O acesso
ao instrumento é serializado: a leitura ao vivo (poller) só roda com a saída
ligada e é parada antes de qualquer outra operação, para nunca haver dois
comandos concorrentes no buffer da fonte.
"""
from __future__ import annotations

import threading
from typing import Callable

from PySide6 import QtCore, QtWidgets

from drivers.exceptions import InstrumentCommunicationError
from gui.widgets.segment_display import SegmentDisplay
from hardware.power_supply import PowerSupplyE363x


class _ActionWorker(QtCore.QThread):
    """Executa uma operação SCPI bloqueante única fora da GUI."""

    done = QtCore.Signal()
    failed = QtCore.Signal(str)

    def __init__(self, action: Callable[[], None], parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            self._action()
            self.done.emit()
        except Exception as exc:  # noqa: BLE001 — a mensagem vai para a GUI, não trava
            self.failed.emit(str(exc))


class _MeasurePoller(QtCore.QThread):
    """Lê tensão/corrente em laço enquanto a saída está ligada."""

    sample = QtCore.Signal(float, float)
    failed = QtCore.Signal(str)

    def __init__(
        self, instrument: PowerSupplyE363x, interval_s: float, parent: QtCore.QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._interval_s = interval_s
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                voltage = self._instrument.measure_voltage()
                current = self._instrument.measure_current()
            except InstrumentCommunicationError as exc:
                self.failed.emit(str(exc))
                return
            self.sample.emit(voltage, current)
            self._stop.wait(self._interval_s)

    def stop(self) -> None:
        self._stop.set()


class ManualOutputDialog(QtWidgets.QDialog):
    """Controle manual de saída (ON/OFF) com leitura ao vivo, estilo bancada."""

    def __init__(
        self,
        instrument: PowerSupplyE363x,
        *,
        simulate: bool,
        port: str | None,
        default_voltage: float = 5.0,
        default_current: float = 1.0,
        poll_interval_s: float = 0.3,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._simulate = simulate
        self._port = port
        self._poll_interval_s = poll_interval_s
        self._output_on = False
        self._busy = False
        self._action_worker: _ActionWorker | None = None
        self._poller: _MeasurePoller | None = None

        self.setWindowTitle("Saída manual — teste rápido")
        self.setModal(True)
        layout = QtWidgets.QVBoxLayout(self)

        warn = QtWidgets.QLabel(
            "Modo manual: energiza a saída fora da sequência do ensaio. "
            "Confirme a placa/cabeamento antes de ligar."
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        setpoint_group = QtWidgets.QGroupBox("Ajustes")
        setpoint_form = QtWidgets.QFormLayout(setpoint_group)
        self.voltage_spin = QtWidgets.QDoubleSpinBox()
        self.voltage_spin.setRange(0.0, 50.0)
        self.voltage_spin.setDecimals(2)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setValue(default_voltage)
        self.current_spin = QtWidgets.QDoubleSpinBox()
        self.current_spin.setRange(0.0, 20.0)
        self.current_spin.setDecimals(3)
        self.current_spin.setSuffix(" A")
        self.current_spin.setValue(default_current)
        setpoint_form.addRow("Tensão:", self.voltage_spin)
        setpoint_form.addRow("Corrente (limite):", self.current_spin)
        layout.addWidget(setpoint_group)

        readouts = QtWidgets.QHBoxLayout()
        self.voltage_display = SegmentDisplay(unit="V", decimals=3)
        self.current_display = SegmentDisplay(unit="A", decimals=3)
        readouts.addWidget(self.voltage_display)
        readouts.addWidget(self.current_display)
        layout.addLayout(readouts)

        self.status_label = QtWidgets.QLabel("Saída: DESLIGADA")
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QHBoxLayout()
        self.on_button = QtWidgets.QPushButton("Ligar saída")
        self.on_button.clicked.connect(self._on_turn_on)
        self.off_button = QtWidgets.QPushButton("Desligar saída")
        self.off_button.setObjectName("dangerButton")
        self.off_button.clicked.connect(self._on_turn_off)
        self.off_button.setEnabled(False)
        self.close_button = QtWidgets.QPushButton("Fechar")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.on_button)
        buttons.addWidget(self.off_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    # -- ligar/desligar -----------------------------------------------------

    def _on_turn_on(self) -> None:
        if self._busy or self._output_on:
            return
        voltage = self.voltage_spin.value()
        current = self.current_spin.value()
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Confirmar energização",
            f"Ligar a saída com {voltage:.2f} V e limite de {current:.3f} A?\n\n"
            "Verifique se a placa e o cabeamento estão corretos antes de confirmar.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        def action() -> None:
            self._instrument.set_simulate(self._simulate)
            self._instrument.set_port(self._port)
            if not self._instrument.is_connected:
                self._instrument.connect()
            self._instrument.apply(voltage, current)
            self._instrument.output_on()

        self._set_busy(True, "Ligando saída…")
        self._run_action(action, on_success=self._after_turned_on)

    def _after_turned_on(self) -> None:
        self._output_on = True
        self._set_busy(False, "Saída: LIGADA")
        self.on_button.setEnabled(False)
        self.off_button.setEnabled(True)
        self.voltage_spin.setEnabled(False)
        self.current_spin.setEnabled(False)
        self._start_poller()

    def _on_turn_off(self) -> None:
        if self._busy or not self._output_on:
            return
        self._stop_poller()
        self._set_busy(True, "Desligando saída…")
        self._run_action(self._instrument.output_off, on_success=self._after_turned_off)

    def _after_turned_off(self) -> None:
        self._output_on = False
        self._set_busy(False, "Saída: DESLIGADA")
        self.on_button.setEnabled(True)
        self.off_button.setEnabled(False)
        self.voltage_spin.setEnabled(True)
        self.current_spin.setEnabled(True)

    # -- infraestrutura -----------------------------------------------------

    def _run_action(self, action: Callable[[], None], on_success: Callable[[], None]) -> None:
        worker = _ActionWorker(action)
        worker.done.connect(on_success)
        worker.failed.connect(self._on_action_failed)
        worker.finished.connect(lambda: setattr(self, "_action_worker", None))
        self._action_worker = worker
        worker.start()

    def _on_action_failed(self, message: str) -> None:
        self._output_on = False
        self._set_busy(False, "Saída: DESLIGADA")
        self.on_button.setEnabled(True)
        self.off_button.setEnabled(False)
        self.voltage_spin.setEnabled(True)
        self.current_spin.setEnabled(True)
        QtWidgets.QMessageBox.warning(self, "Falha na saída manual", message)

    def _start_poller(self) -> None:
        poller = _MeasurePoller(self._instrument, self._poll_interval_s)
        poller.sample.connect(self._on_sample)
        poller.failed.connect(self._on_action_failed)
        self._poller = poller
        poller.start()

    def _stop_poller(self) -> None:
        if self._poller is not None:
            self._poller.stop()
            self._poller.wait(2000)
            self._poller = None

    def _on_sample(self, voltage: float, current: float) -> None:
        self.voltage_display.set_value(voltage)
        self.current_display.set_value(current)

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self.status_label.setText(status)
        if busy:
            self.on_button.setEnabled(False)
            self.off_button.setEnabled(False)

    def _shutdown(self) -> None:
        """Failsafe: para a leitura, desliga a saída e fecha a porta, sempre."""
        self._stop_poller()
        if self._action_worker is not None:
            self._action_worker.wait(3000)
        try:
            if self._instrument.is_connected:
                self._instrument.disconnect()  # on_disconnecting já tenta OUTPUT OFF
        except InstrumentCommunicationError:
            pass

    def reject(self) -> None:
        self._shutdown()
        super().reject()

    def closeEvent(self, event: QtCore.QEvent) -> None:
        self._shutdown()
        super().closeEvent(event)
