"""Tela de parâmetros de teste (seção 3.2).

Define tensão nominal, limites de tensão (referência visual, nunca gatilho
automático — seção 3.3), corrente máxima, duração e a sequência multi-step
opcional de potência. Persiste como `TestParameterConfig` associado à placa
e traduz o config persistido em um `TestRunConfig` consumível pelo state
machine. Não conhece o instrumento nem o state machine além desse DTO.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from core.state_machine import TestRunConfig
from database.models import Board, PowerStep, TestParameterConfig
from database.repositories import TestParameterConfigRepository


class TestParametersView(QtWidgets.QWidget):
    parameters_submitted = QtCore.Signal(dict)
    back_requested = QtCore.Signal()

    _COLUMN_LABELS = ("Tensão (V)", "Corrente máx. (A)", "Duração (s)")

    def __init__(
        self,
        config_repo: TestParameterConfigRepository,
        test_defaults: dict,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_repo = config_repo
        self._test_defaults = test_defaults
        self._board: Board | None = None

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.addWidget(scroll)

        form_container = QtWidgets.QWidget()
        scroll.setWidget(form_container)
        form_layout = QtWidgets.QVBoxLayout(form_container)

        self.board_label = QtWidgets.QLabel("Nenhuma placa selecionada.")
        form_layout.addWidget(self.board_label)

        history_group = QtWidgets.QGroupBox("Configurações salvas para esta placa")
        history_layout = QtWidgets.QHBoxLayout(history_group)
        self.history_combo = QtWidgets.QComboBox()
        self.load_button = QtWidgets.QPushButton("Carregar")
        self.load_button.clicked.connect(self._on_load_history)
        history_layout.addWidget(self.history_combo, stretch=1)
        history_layout.addWidget(self.load_button)
        form_layout.addWidget(history_group)

        limits_group = QtWidgets.QGroupBox("Tensão, corrente e duração")
        limits_form = QtWidgets.QFormLayout(limits_group)

        self.config_name_edit = QtWidgets.QLineEdit()
        self.nominal_voltage_spin = self._make_double_spin(0.0, 50.0, 2, " V")
        self.voltage_min_spin = self._make_double_spin(0.0, 50.0, 2, " V")
        self.voltage_max_spin = self._make_double_spin(0.0, 50.0, 2, " V")
        self.current_max_spin = self._make_double_spin(0.0, 20.0, 3, " A")
        self.test_duration_spin = self._make_double_spin(0.0, 86400.0, 1, " s")
        self.test_duration_spin.setValue(60.0)

        limits_form.addRow("Nome da configuração:", self.config_name_edit)
        limits_form.addRow("Tensão nominal:", self.nominal_voltage_spin)
        limits_form.addRow("Tensão mínima (referência):", self.voltage_min_spin)
        limits_form.addRow("Tensão máxima (referência):", self.voltage_max_spin)
        limits_form.addRow("Corrente máxima:", self.current_max_spin)
        limits_form.addRow("Duração do teste (passo único):", self.test_duration_spin)
        form_layout.addWidget(limits_group)

        advanced_group = QtWidgets.QGroupBox("Parâmetros avançados de monitoramento")
        advanced_form = QtWidgets.QFormLayout(advanced_group)
        self.polling_rate_spin = self._make_double_spin(0.1, 10.0, 2, " Hz")
        self.polling_rate_spin.setValue(self._test_defaults["polling_rate_hz"])
        self.stabilization_timeout_spin = self._make_double_spin(0.5, 300.0, 1, " s")
        self.stabilization_timeout_spin.setValue(self._test_defaults["stabilization_timeout_s"])
        self.stabilization_tolerance_spin = self._make_double_spin(0.0, 5.0, 3, " V")
        self.stabilization_tolerance_spin.setValue(self._test_defaults["stabilization_tolerance_v"])
        self.consecutive_failures_spin = QtWidgets.QSpinBox()
        self.consecutive_failures_spin.setRange(1, 100)
        self.consecutive_failures_spin.setValue(self._test_defaults["monitoring_consecutive_failures_limit"])

        advanced_form.addRow("Taxa de amostragem:", self.polling_rate_spin)
        advanced_form.addRow("Timeout de estabilização:", self.stabilization_timeout_spin)
        advanced_form.addRow("Tolerância de estabilização:", self.stabilization_tolerance_spin)
        advanced_form.addRow("Falhas consecutivas até erro de comunicação:", self.consecutive_failures_spin)
        form_layout.addWidget(advanced_group)

        sequence_group = QtWidgets.QGroupBox(
            "Sequência multi-step de potência (opcional — vazio usa o passo único acima)"
        )
        sequence_layout = QtWidgets.QVBoxLayout(sequence_group)
        self.sequence_table = QtWidgets.QTableWidget(0, len(self._COLUMN_LABELS))
        self.sequence_table.setHorizontalHeaderLabels(self._COLUMN_LABELS)
        self.sequence_table.horizontalHeader().setStretchLastSection(True)
        sequence_layout.addWidget(self.sequence_table)

        sequence_buttons = QtWidgets.QHBoxLayout()
        self.add_step_button = QtWidgets.QPushButton("Adicionar passo")
        self.add_step_button.clicked.connect(self._on_add_step)
        self.remove_step_button = QtWidgets.QPushButton("Remover passo selecionado")
        self.remove_step_button.clicked.connect(self._on_remove_step)
        sequence_buttons.addWidget(self.add_step_button)
        sequence_buttons.addWidget(self.remove_step_button)
        sequence_buttons.addStretch()
        sequence_layout.addLayout(sequence_buttons)
        form_layout.addWidget(sequence_group)

        actions_row = QtWidgets.QHBoxLayout()
        self.back_button = QtWidgets.QPushButton("Voltar")
        self.back_button.clicked.connect(self.back_requested.emit)
        self.submit_button = QtWidgets.QPushButton("Salvar e continuar")
        self.submit_button.clicked.connect(self._on_submit)
        actions_row.addWidget(self.back_button)
        actions_row.addStretch()
        actions_row.addWidget(self.submit_button)
        form_layout.addLayout(actions_row)
        form_layout.addStretch()

    @staticmethod
    def _make_double_spin(minimum: float, maximum: float, decimals: int, suffix: str) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        return spin

    def set_board(self, board: Board) -> None:
        self._board = board
        self.board_label.setText(f"Placa: {board.code} (P/N {board.part_number}, rev. {board.revision})")
        self.refresh_history()

    def refresh_history(self) -> None:
        self.history_combo.clear()
        if self._board is None or self._board.id is None:
            return
        for config in self._config_repo.list_for_board(self._board.id):
            self.history_combo.addItem(config.name, userData=config)

    def _on_load_history(self) -> None:
        config: TestParameterConfig | None = self.history_combo.currentData()
        if config is None:
            return
        self.config_name_edit.setText(config.name)
        self.nominal_voltage_spin.setValue(config.nominal_voltage)
        self.voltage_min_spin.setValue(config.voltage_min)
        self.voltage_max_spin.setValue(config.voltage_max)
        self.current_max_spin.setValue(config.current_max)
        self.test_duration_spin.setValue(config.test_duration_s)
        self.sequence_table.setRowCount(0)
        for step in config.power_sequence:
            self._append_step_row(step.voltage, step.current, step.duration_s)

    def _on_add_step(self) -> None:
        self._append_step_row(
            self.nominal_voltage_spin.value(),
            self.current_max_spin.value(),
            self.test_duration_spin.value(),
        )

    def _append_step_row(self, voltage: float, current: float, duration_s: float) -> None:
        row = self.sequence_table.rowCount()
        self.sequence_table.insertRow(row)
        for column, value in enumerate((voltage, current, duration_s)):
            self.sequence_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

    def _on_remove_step(self) -> None:
        row = self.sequence_table.currentRow()
        if row >= 0:
            self.sequence_table.removeRow(row)

    def _read_power_sequence(self) -> list[PowerStep] | None:
        steps: list[PowerStep] = []
        for row in range(self.sequence_table.rowCount()):
            try:
                voltage = float(self.sequence_table.item(row, 0).text())
                current = float(self.sequence_table.item(row, 1).text())
                duration_s = float(self.sequence_table.item(row, 2).text())
            except (AttributeError, ValueError):
                QtWidgets.QMessageBox.warning(
                    self, "Sequência inválida", f"Linha {row + 1} da sequência tem valor inválido."
                )
                return None
            steps.append(PowerStep(voltage=voltage, current=current, duration_s=duration_s))
        return steps

    def _on_submit(self) -> None:
        if self._board is None:
            QtWidgets.QMessageBox.warning(self, "Placa não definida", "Cadastre a placa antes de definir os parâmetros.")
            return

        config_name = self.config_name_edit.text().strip()
        if not config_name:
            QtWidgets.QMessageBox.warning(self, "Campo obrigatório", "Informe um nome para a configuração.")
            return

        if self.voltage_min_spin.value() > self.voltage_max_spin.value():
            QtWidgets.QMessageBox.warning(
                self, "Limites inválidos", "Tensão mínima não pode ser maior que a tensão máxima."
            )
            return

        power_sequence = self._read_power_sequence()
        if power_sequence is None:
            return

        config = TestParameterConfig(
            id=None,
            board_id=self._board.id,
            name=config_name,
            nominal_voltage=self.nominal_voltage_spin.value(),
            voltage_min=self.voltage_min_spin.value(),
            voltage_max=self.voltage_max_spin.value(),
            current_max=self.current_max_spin.value(),
            test_duration_s=self.test_duration_spin.value(),
            power_sequence=power_sequence,
        )
        saved_config = self._config_repo.save(config)
        self.refresh_history()

        run_config = TestRunConfig(
            nominal_voltage=saved_config.nominal_voltage,
            voltage_min=saved_config.voltage_min,
            voltage_max=saved_config.voltage_max,
            current_max=saved_config.current_max,
            test_duration_s=saved_config.test_duration_s,
            power_sequence=saved_config.power_sequence,
            polling_rate_hz=self.polling_rate_spin.value(),
            stabilization_timeout_s=self.stabilization_timeout_spin.value(),
            stabilization_tolerance_v=self.stabilization_tolerance_spin.value(),
            monitoring_consecutive_failures_limit=self.consecutive_failures_spin.value(),
        )

        self.parameters_submitted.emit(
            {"test_parameter_config": saved_config, "run_config": run_config}
        )
