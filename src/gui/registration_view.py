"""Tela de cadastro de teste (seção 3.2).

Coleta os dados de identificação da placa/operador e cria (ou reaproveita)
os registros de Board/Operator/TestSession no banco. Não conhece o
state machine nem a fonte — só persistência e validação de formulário.
"""
from __future__ import annotations

import datetime as dt

from PySide6 import QtCore, QtWidgets

from database.models import Operator
from database.repositories import BoardRepository, OperatorRepository
from version import APP_VERSION


class RegistrationView(QtWidgets.QWidget):
    registration_submitted = QtCore.Signal(dict)

    def __init__(
        self,
        operator_repo: OperatorRepository,
        board_repo: BoardRepository,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._operator_repo = operator_repo
        self._board_repo = board_repo

        version_label = QtWidgets.QLabel(f"Versão {APP_VERSION}")
        version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        version_label.setStyleSheet("color: gray; font-size: 11px;")

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.addWidget(version_label)
        outer_layout.addWidget(scroll)

        form_container = QtWidgets.QWidget()
        scroll.setWidget(form_container)

        operator_group = QtWidgets.QGroupBox("Cadastro do Operador")
        operator_form = QtWidgets.QFormLayout(operator_group)

        self.operator_combo = QtWidgets.QComboBox()
        self.operator_combo.setEditable(True)
        self.operator_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.operator_combo.currentTextChanged.connect(self._on_operator_changed)
        self.if_edit = QtWidgets.QLineEdit()

        operator_form.addRow("Operador:", self.operator_combo)
        operator_form.addRow("IF:", self.if_edit)

        group = QtWidgets.QGroupBox("Identificação da placa e do teste")
        form = QtWidgets.QFormLayout(group)

        self.code_edit = QtWidgets.QLineEdit()
        self.part_number_edit = QtWidgets.QLineEdit()
        self.revision_edit = QtWidgets.QLineEdit()
        self.serial_number_edit = QtWidgets.QLineEdit()
        self.production_order_edit = QtWidgets.QLineEdit()
        self.observations_edit = QtWidgets.QTextEdit()
        self.observations_edit.setMaximumHeight(80)
        self.datetime_label = QtWidgets.QLabel()

        form.addRow("Código da placa:", self.code_edit)
        form.addRow("Part Number (P/N):", self.part_number_edit)
        form.addRow("Revisão:", self.revision_edit)
        form.addRow("Número de série (S/N):", self.serial_number_edit)
        form.addRow("Ordem de produção:", self.production_order_edit)
        form.addRow("Observações:", self.observations_edit)
        form.addRow("Data/hora:", self.datetime_label)

        self.submit_button = QtWidgets.QPushButton("Iniciar cadastro do teste")
        self.submit_button.clicked.connect(self._on_submit)

        form_layout = QtWidgets.QVBoxLayout(form_container)
        form_layout.addWidget(operator_group)
        form_layout.addWidget(group)
        form_layout.addWidget(self.submit_button)
        form_layout.addStretch()

        self._clock_timer = QtCore.QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        self.refresh_operator_history()

    def refresh_operator_history(self) -> None:
        self.operator_combo.clear()
        for operator in self._operator_repo.list_all():
            self.operator_combo.addItem(operator.name, userData=operator)

    def _on_operator_changed(self, name: str) -> None:
        index = self.operator_combo.findText(name)
        operator: Operator | None = self.operator_combo.itemData(index) if index >= 0 else None
        self.if_edit.setText(operator.if_number or "" if operator else "")

    def _update_clock(self) -> None:
        self.datetime_label.setText(dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    def _on_submit(self) -> None:
        code = self.code_edit.text().strip()
        part_number = self.part_number_edit.text().strip()
        revision = self.revision_edit.text().strip()
        serial_number = self.serial_number_edit.text().strip()
        operator_name = self.operator_combo.currentText().strip()
        if_number = self.if_edit.text().strip()

        missing = [
            label
            for label, value in (
                ("Código da placa", code),
                ("P/N", part_number),
                ("Revisão", revision),
                ("S/N", serial_number),
                ("Operador", operator_name),
                ("IF", if_number),
            )
            if not value
        ]
        if missing:
            QtWidgets.QMessageBox.warning(
                self, "Campos obrigatórios", "Preencha: " + ", ".join(missing)
            )
            return

        operator: Operator = self._operator_repo.get_or_create(operator_name, if_number)
        board = self._board_repo.get_or_create(code, part_number, revision)
        self.refresh_operator_history()

        self.registration_submitted.emit(
            {
                "board": board,
                "operator": operator,
                "serial_number": serial_number,
                "production_order": self.production_order_edit.text().strip() or None,
                "observations": self.observations_edit.toPlainText().strip() or None,
            }
        )
