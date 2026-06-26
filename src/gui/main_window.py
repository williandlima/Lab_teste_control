"""Janela principal: orquestra o fluxo Cadastro -> Parâmetros -> Monitoramento
-> Avaliação manual (seção 3.2/3.3).

O state machine roda em uma QThread dedicada (`TestRunWorker`) para nunca
bloquear a GUI (seção 4). Os hooks `on_state_changed`/`on_sample`/`on_event`
de `core/state_machine.py` são callbacks simples — aqui são conectados a
sinais Qt do worker, que o framework já entrega na thread da GUI via
conexão em fila quando emitidos de outra thread.

O status técnico da sessão (`TestSessionStatus`) é fixado por esta classe
no instante em que o worker termina, a partir do `termination_reason` do
state machine — nunca pela tela de avaliação, que só grava o julgamento
manual do operador (`Evaluation`), um campo deliberadamente separado.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import asdict
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from config import AppConfig
from core.sampling_buffer import Sample, SamplingBuffer
from core.state_machine import TestRunConfig, TestState, TestStateMachine
from database.database import Database
from database.models import (
    Board,
    EventLogEntry,
    MonitoredSample,
    Operator,
    TestSession,
    TestSessionStatus,
)
from database.repositories import (
    BoardRepository,
    EvaluationRepository,
    EventLogRepository,
    MonitoredSampleRepository,
    OperatorRepository,
    TestParameterConfigRepository,
    TestSessionRepository,
)
from drivers.exceptions import InstrumentCommunicationError
from gui.evaluation_view import EvaluationView
from gui.registration_view import RegistrationView
from gui.styles import load_theme
from gui.test_parameters_view import TestParametersView
from gui.widgets.header_bar import HeaderBar
from gui.widgets.live_chart import LiveChart
from gui.widgets.segment_display import SegmentDisplay
from gui.widgets.status_badge import StatusBadge
from hardware.power_supply import PowerSupplyE363x
from logger import UI_LOG_BUFFER
from reports.excel_report import generate_excel_report
from reports.pdf_report import generate_pdf_report
from reports.report_data import assemble_report_data
from reports.template_engine import report_filename
from reports.word_report import generate_word_report

_logger = logging.getLogger("app")

_TERMINATION_TO_SESSION_STATUS = {
    TestState.COMPLETED: TestSessionStatus.COMPLETED,
    TestState.ABORTED: TestSessionStatus.ABORTED,
    TestState.COMM_ERROR: TestSessionStatus.COMM_ERROR,
    TestState.FAULTED: TestSessionStatus.FAULTED,
}


class TestRunWorker(QtCore.QThread):
    """Executa `TestStateMachine.run()` fora da thread da GUI."""

    state_changed = QtCore.Signal(str)
    sample_received = QtCore.Signal(object)
    event_logged = QtCore.Signal(str, str)

    def __init__(
        self, state_machine: TestStateMachine | None = None, parent: QtCore.QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.state_machine = state_machine

    def run(self) -> None:
        self.state_machine.run()


class ConnectionProbeWorker(QtCore.QThread):
    """Roda `instrument.test_connection()` fora da GUI (a sonda é bloqueante).

    Emite `succeeded` com a string de identificação ou `failed` com a mensagem
    diagnóstica já tratada (timeout vs framing), nunca um traceback cru.
    """

    succeeded = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(
        self,
        instrument: PowerSupplyE363x,
        port: str,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._instrument = instrument
        self._port = port

    def run(self) -> None:
        try:
            self._instrument.set_port(self._port or None)
            identity = self._instrument.test_connection()
            self.succeeded.emit(identity)
        except InstrumentCommunicationError as exc:
            self.failed.emit(str(exc))


class _MonitoringPanel(QtWidgets.QWidget):
    """Tela de status/leituras ao vivo (seção 11.1) — readouts VFD + badges + gráfico."""

    abort_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        self.state_label = QtWidgets.QLabel("Estado: —")
        layout.addWidget(self.state_label)

        badges_layout = QtWidgets.QHBoxLayout()
        self.remote_badge = StatusBadge("REMOTO")
        self.output_badge = StatusBadge("SAÍDA")
        self.protection_badge = StatusBadge("PROTEÇÃO")
        for badge in (self.remote_badge, self.output_badge, self.protection_badge):
            badges_layout.addWidget(badge)
        badges_layout.addStretch()
        layout.addLayout(badges_layout)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        readouts_widget = QtWidgets.QWidget()
        readouts_layout = QtWidgets.QVBoxLayout(readouts_widget)
        self.voltage_display = SegmentDisplay(unit="V", decimals=3)
        self.current_display = SegmentDisplay(unit="A", decimals=3)
        readouts_layout.addWidget(self.voltage_display)
        readouts_layout.addWidget(self.current_display)
        readouts_layout.addStretch()
        splitter.addWidget(readouts_widget)

        self.live_chart = LiveChart()
        splitter.addWidget(self.live_chart)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        self.abort_button = QtWidgets.QPushButton("Abortar teste")
        self.abort_button.setObjectName("dangerButton")
        self.abort_button.clicked.connect(self.abort_requested.emit)
        layout.addWidget(self.abort_button)

        self.event_log_edit = QtWidgets.QPlainTextEdit()
        self.event_log_edit.setReadOnly(True)
        self.event_log_edit.setMaximumHeight(80)
        layout.addWidget(self.event_log_edit)

    def reset(self, voltage_min: float, voltage_max: float, duration_s: float, current_max: float) -> None:
        self.state_label.setText("Estado: —")
        self.remote_badge.set_unknown()
        self.output_badge.set_unknown()
        self.protection_badge.set_active(True)
        self.live_chart.clear()
        self.live_chart.set_voltage_limits(voltage_min, voltage_max, duration_s)
        self.live_chart.set_current_range(current_max)
        self.event_log_edit.clear()

    def on_state_changed(self, state_value: str) -> None:
        self.state_label.setText(f"Estado: {state_value}")
        state = TestState(state_value)
        self.remote_badge.set_active(
            state
            not in (TestState.IDLE, TestState.INITIALIZING, TestState.CHECKING_COMMUNICATION)
        )
        self.output_badge.set_active(
            state in (TestState.APPLYING_VOLTAGE, TestState.STABILIZING, TestState.MONITORING)
        )

    def on_sample(self, sample: Sample) -> None:
        self.voltage_display.set_value(sample.voltage)
        self.current_display.set_value(sample.current)

    def append_event(self, level: str, message: str) -> None:
        self.event_log_edit.appendPlainText(f"[{level}] {message}")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_config: AppConfig, database: Database, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_config = app_config
        self._db = database

        self._operator_repo = OperatorRepository(database)
        self._board_repo = BoardRepository(database)
        self._config_repo = TestParameterConfigRepository(database)
        self._session_repo = TestSessionRepository(database)
        self._sample_repo = MonitoredSampleRepository(database)
        self._evaluation_repo = EvaluationRepository(database)
        self._event_repo = EventLogRepository(database)

        self._instrument = PowerSupplyE363x(app_config.serial, app_config.reconnection)

        self._board: Board | None = None
        self._operator: Operator | None = None
        self._registration_data: dict | None = None
        self._session: TestSession | None = None
        self._state_machine: TestStateMachine | None = None
        self._worker: TestRunWorker | None = None
        self._probe_worker: ConnectionProbeWorker | None = None
        self._live_samples: list[Sample] = []
        self._last_log_text = ""

        self.setWindowTitle(f"{app_config.branding.company_name} — FCT")
        self.setStyleSheet(load_theme(app_config.branding))

        self.header = HeaderBar(app_config.branding)
        self.header.test_connection_requested.connect(self._on_test_connection)
        # Estado inicial do botão "Simulação" segue o config (serial.simulate).
        self.header.set_simulation_enabled(app_config.serial.simulate)

        self.registration_view = RegistrationView(self._operator_repo, self._board_repo)
        self.parameters_view = TestParametersView(self._config_repo, asdict(app_config.test_defaults))
        self.monitoring_panel = _MonitoringPanel()
        self.evaluation_view = EvaluationView(self._evaluation_repo)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.registration_view)
        self.stack.addWidget(self.parameters_view)
        self.stack.addWidget(self.monitoring_panel)
        self.stack.addWidget(self.evaluation_view)
        self.stack.currentChanged.connect(self._update_step_indicator)

        # Log da aplicação: faixa fina sempre visível (espaço reduzido).
        self.app_log_edit = QtWidgets.QPlainTextEdit()
        self.app_log_edit.setReadOnly(True)
        self.app_log_edit.setFixedHeight(44)

        log_row = QtWidgets.QHBoxLayout()
        log_row.setContentsMargins(0, 0, 0, 0)
        log_label = QtWidgets.QLabel("Log:")
        log_row.addWidget(log_label)
        log_row.addWidget(self.app_log_edit, stretch=1)

        central = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central)
        central_layout.addWidget(self.header)
        central_layout.addWidget(self.stack, stretch=1)
        central_layout.addLayout(log_row)
        self.setCentralWidget(central)

        self.registration_view.registration_submitted.connect(self._on_registration_submitted)
        self.parameters_view.parameters_submitted.connect(self._on_parameters_submitted)
        self.monitoring_panel.abort_requested.connect(self._on_abort_requested)
        self.evaluation_view.evaluation_submitted.connect(self._on_evaluation_submitted)

        self._update_step_indicator(self.stack.currentIndex())

        self._log_timer = QtCore.QTimer(self)
        self._log_timer.timeout.connect(self._refresh_log_panel)
        self._log_timer.start(1000)

    def _on_registration_submitted(self, data: dict) -> None:
        self._board = data["board"]
        self._operator = data["operator"]
        self._registration_data = data
        self.parameters_view.set_board(self._board)
        self.stack.setCurrentWidget(self.parameters_view)

    def _on_parameters_submitted(self, data: dict) -> None:
        config = data["test_parameter_config"]
        run_config: TestRunConfig = data["run_config"]
        registration = self._registration_data
        assert self._board is not None and self._operator is not None and registration is not None

        session = self._session_repo.create(
            TestSession(
                id=None,
                board_id=self._board.id,
                serial_number=registration["serial_number"],
                operator_id=self._operator.id,
                test_parameter_config_id=config.id,
                config_snapshot_json=json.dumps(asdict(run_config)),
                production_order=registration["production_order"],
                observations=registration["observations"],
                status=TestSessionStatus.RUNNING,
                started_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        self._session = session
        self._live_samples = []

        buffer = SamplingBuffer(
            live_buffer_maxlen=self._app_config.test_defaults.live_buffer_maxlen,
            batch_size=self._app_config.test_defaults.sample_batch_size,
            batch_interval_s=self._app_config.test_defaults.sample_batch_interval_s,
            on_flush=lambda samples: self._persist_samples(session.id, samples),
        )

        worker = TestRunWorker()
        state_machine = TestStateMachine(
            instrument=self._instrument,
            sampling_buffer=buffer,
            config=run_config,
            on_state_changed=lambda state: worker.state_changed.emit(state.value),
            on_sample=lambda sample: worker.sample_received.emit(sample),
            on_event=lambda level, message: worker.event_logged.emit(level, message),
        )
        worker.state_machine = state_machine
        self._state_machine = state_machine
        self._worker = worker

        worker.state_changed.connect(self.monitoring_panel.on_state_changed)
        worker.sample_received.connect(self._on_sample)
        worker.event_logged.connect(self._on_event)
        worker.finished.connect(self._on_worker_finished)

        # A porta escolhida pelo operador no cabeçalho vale para o teste real.
        self._instrument.set_port(self.header.selected_port() or None)
        # Modo simulação (fonte virtual) segue o botão do cabeçalho.
        self._instrument.set_simulate(self.header.simulation_enabled())

        self.monitoring_panel.reset(
            run_config.voltage_min, run_config.voltage_max, run_config.test_duration_s, run_config.current_max
        )
        self.header.test_button.setEnabled(False)  # sem sondar a porta durante o teste
        self.stack.setCurrentWidget(self.monitoring_panel)
        worker.start()

    def _persist_samples(self, session_id: int, samples: list[Sample]) -> None:
        self._sample_repo.insert_batch(
            [
                MonitoredSample(
                    id=None,
                    test_session_id=session_id,
                    timestamp=dt.datetime.fromtimestamp(s.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f"),
                    step_index=s.step_index,
                    voltage_measured=s.voltage,
                    current_measured=s.current,
                )
                for s in samples
            ]
        )

    def _on_sample(self, sample: Sample) -> None:
        self._live_samples.append(sample)
        self.monitoring_panel.on_sample(sample)
        decimated = SamplingBuffer.decimate(self._live_samples, max_points=500)
        self.monitoring_panel.live_chart.update_samples(decimated)

    def _on_event(self, level: str, message: str) -> None:
        self.monitoring_panel.append_event(level, message)
        self._event_repo.add(
            EventLogEntry(
                id=None,
                test_session_id=self._session.id if self._session else None,
                timestamp=None,
                level=level,
                source="state_machine",
                message=message,
            )
        )

    def _on_abort_requested(self) -> None:
        if self._state_machine is not None:
            self._state_machine.request_abort()

    def _on_worker_finished(self) -> None:
        assert self._state_machine is not None and self._session is not None
        termination = self._state_machine.termination_reason
        status = _TERMINATION_TO_SESSION_STATUS.get(termination, TestSessionStatus.FAULTED)
        self._session_repo.update_status(
            self._session.id, status, finished_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.header.test_button.setEnabled(True)

        # COMM_ERROR = o teste NÃO chegou a comunicar com a fonte (falha já na
        # 1ª etapa). Não faz sentido ir para a avaliação manual com uma sessão
        # sem amostras — isso é o que fazia a tela "abrir e já encerrar". Em vez
        # disso, avisa o operador com uma mensagem acionável e volta aos
        # parâmetros para nova tentativa (a placa/operador continuam carregados).
        if status == TestSessionStatus.COMM_ERROR:
            self.header.set_connection_state(False, "Erro de comunicação durante o teste.")
            self._session = None
            self._state_machine = None
            self._worker = None
            QtWidgets.QMessageBox.warning(
                self,
                "O teste não executou",
                "Falha de comunicação com a fonte — o ensaio não chegou a iniciar.\n\n"
                "Verifique:\n"
                "• a porta COM e o cabo/adaptador (use \"Testar conexão\");\n"
                "• o baudrate/paridade iguais ao painel frontal da fonte;\n"
                "• ou marque \"Simulação\" no cabeçalho para rodar sem hardware.",
            )
            self.stack.setCurrentWidget(self.parameters_view)
            return

        samples = self._sample_repo.list_for_session(self._session.id)
        self.evaluation_view.load_session(self._session, self._operator, self._state_machine, samples)
        self.stack.setCurrentWidget(self.evaluation_view)

    def _on_evaluation_submitted(self, data: dict) -> None:
        session: TestSession = data["session"]
        self._save_report(session.id)

        self._session = None
        self._state_machine = None
        self._worker = None
        self._board = None
        self._operator = None
        self._registration_data = None
        self.registration_view.refresh_operator_history()
        self.registration_view.clear_form()
        self.stack.setCurrentWidget(self.registration_view)

    def _save_report(self, test_session_id: int) -> None:
        """Salva o relatório do ensaio com diálogo "Salvar como" do Windows.

        O operador escolhe pasta E nome do arquivo no diálogo nativo (mesmo
        modelo do Word). São gerados os três formatos (Word/Excel/PDF) com o
        nome escolhido. Cancelar o diálogo não impede o avanço para o próximo
        cadastro — só pula a geração do relatório.
        """
        data = assemble_report_data(
            test_session_id,
            self._session_repo,
            self._board_repo,
            self._operator_repo,
            self._sample_repo,
            self._evaluation_repo,
            self._event_repo,
        )

        default_name = report_filename(data, "docx")
        default_path = str(self._app_config.paths.exports_dir / default_name)
        chosen, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Salvar relatório do ensaio",
            default_path,
            "Relatório FCT (*.docx *.xlsx *.pdf)",
        )
        if not chosen:
            return

        chosen_path = Path(chosen)
        output_dir = chosen_path.parent
        base_name = chosen_path.stem
        try:
            saved_paths = [
                generate_word_report(data, self._app_config.branding, output_dir, base_name),
                generate_excel_report(data, self._app_config.branding, output_dir, base_name),
                generate_pdf_report(data, self._app_config.branding, output_dir, base_name),
            ]
        except Exception as exc:  # noqa: BLE001 — falha de geração não pode travar o fluxo
            _logger.exception("Falha ao gerar relatório do ensaio")
            QtWidgets.QMessageBox.warning(self, "Erro ao salvar relatório", str(exc))
            return

        QtWidgets.QMessageBox.information(
            self,
            "Relatório salvo",
            "Relatório salvo em:\n" + "\n".join(str(path) for path in saved_paths),
        )

    _STEP_NAMES = {0: "Cadastro", 1: "Parâmetros", 2: "Monitoramento", 3: "Avaliação manual"}

    def _update_step_indicator(self, index: int) -> None:
        self.header.set_step(self._STEP_NAMES.get(index, ""))

    def _on_test_connection(self, port: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            QtWidgets.QMessageBox.information(
                self, "Teste em andamento", "Aguarde o término do teste para sondar a porta."
            )
            return
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return
        self.header.set_testing(True)
        self.header.set_connection_unknown("Sondando a fonte…")
        self._instrument.set_simulate(self.header.simulation_enabled())
        probe = ConnectionProbeWorker(self._instrument, port)
        probe.succeeded.connect(self._on_probe_success)
        probe.failed.connect(self._on_probe_failure)
        probe.finished.connect(lambda: self.header.set_testing(False))
        self._probe_worker = probe
        probe.start()

    def _on_probe_success(self, identity: str) -> None:
        self.header.set_connection_state(True, f"Conectada: {identity}")
        QtWidgets.QMessageBox.information(
            self, "Conexão OK", f"Fonte identificada:\n{identity}"
        )

    def _on_probe_failure(self, message: str) -> None:
        self.header.set_connection_state(False, message)
        QtWidgets.QMessageBox.warning(self, "Falha na conexão", message)

    def _refresh_log_panel(self) -> None:
        # Só redesenha quando o conteúdo muda (o deque satura em 200 linhas, então
        # comparar por tamanho não basta): evita reescrever todo o QPlainTextEdit
        # a cada segundo e o salto de scroll que isso causava.
        text = "\n".join(UI_LOG_BUFFER)
        if text == self._last_log_text:
            return
        self._last_log_text = text
        self.app_log_edit.setPlainText(text)
        self.app_log_edit.verticalScrollBar().setValue(self.app_log_edit.verticalScrollBar().maximum())

    def closeEvent(self, event: QtCore.QEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        if self._probe_worker is not None and self._probe_worker.isRunning():
            self._probe_worker.wait(3000)
        if self._instrument.is_connected:
            self._instrument.disconnect()
        super().closeEvent(event)
