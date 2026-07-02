"""Testes 'gui' (offscreen) do botão "Excluir" em operadores (Cadastro) e
configurações salvas (Parâmetros) -- resposta à dúvida do usuário sobre como
limpar operadores/testes carregados: não existia essa opção pela GUI.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6")

pytestmark = pytest.mark.gui

from PySide6 import QtWidgets

from database.database import Database
from database.models import TestSession, TestSessionStatus
from database.repositories import (
    BoardRepository,
    OperatorRepository,
    TestParameterConfigRepository,
    TestSessionRepository,
)
from database.models import TestParameterConfig
from gui.registration_view import RegistrationView
from gui.test_parameters_view import TestParametersView


def _confirm_yes():
    return patch.object(
        QtWidgets.QMessageBox, "question",
        return_value=QtWidgets.QMessageBox.StandardButton.Yes,
    )


# -- Operador (Cadastro) ------------------------------------------------------


def test_delete_operator_removes_unused_entry_from_combo(qtbot, tmp_path: Path) -> None:
    db = Database(tmp_path / "del_operator.db")
    db.connect()
    operator_repo = OperatorRepository(db)
    operator_repo.get_or_create("Duplicado")
    view = RegistrationView(operator_repo, BoardRepository(db))
    qtbot.addWidget(view)
    assert view.operator_combo.count() == 1

    view.operator_combo.setCurrentIndex(0)
    with _confirm_yes():
        view.delete_operator_button.click()

    assert view.operator_combo.count() == 0
    assert operator_repo.list_all() == []
    db.close()


def test_delete_operator_with_nothing_selected_warns_and_does_not_crash(
    qtbot, tmp_path: Path
) -> None:
    db = Database(tmp_path / "del_operator_none.db")
    db.connect()
    view = RegistrationView(OperatorRepository(db), BoardRepository(db))
    qtbot.addWidget(view)
    view.operator_combo.setCurrentIndex(-1)

    with patch.object(QtWidgets.QMessageBox, "warning") as mock_warning:
        view.delete_operator_button.click()

    mock_warning.assert_called_once()
    db.close()


def test_delete_operator_blocked_when_used_by_a_test_session(qtbot, tmp_path: Path) -> None:
    db = Database(tmp_path / "del_operator_blocked.db")
    db.connect()
    operator_repo = OperatorRepository(db)
    board_repo = BoardRepository(db)
    operator = operator_repo.get_or_create("Com ensaio")
    board = board_repo.get_or_create("PCB-1", "PN-1", "A")
    TestSessionRepository(db).create(
        TestSession(
            id=None, board_id=board.id, serial_number="SN-1", operator_id=operator.id,
            test_parameter_config_id=None, config_snapshot_json="{}", production_order=None,
            observations=None, status=TestSessionStatus.COMPLETED,
        )
    )
    view = RegistrationView(operator_repo, board_repo)
    qtbot.addWidget(view)
    view.operator_combo.setCurrentIndex(0)

    with _confirm_yes(), patch.object(QtWidgets.QMessageBox, "warning") as mock_warning:
        view.delete_operator_button.click()

    mock_warning.assert_called_once()
    assert view.operator_combo.count() == 1  # não foi removido
    db.close()


# -- Configuração salva (Parâmetros) ------------------------------------------


def test_delete_history_config_removes_unused_entry_from_combo(qtbot, tmp_path: Path) -> None:
    db = Database(tmp_path / "del_config.db")
    db.connect()
    board_repo = BoardRepository(db)
    config_repo = TestParameterConfigRepository(db)
    board = board_repo.get_or_create("PCB-1", "PN-1", "A")
    config_repo.save(
        TestParameterConfig(
            id=None, board_id=board.id, name="Preset por engano", nominal_voltage=5.0,
            voltage_min=4.5, voltage_max=5.5, current_max=1.0, test_duration_s=60.0,
            power_sequence=[],
        )
    )
    view = TestParametersView(config_repo, {
        "polling_rate_hz": 1.0, "stabilization_timeout_s": 5.0,
        "stabilization_tolerance_v": 0.05, "monitoring_consecutive_failures_limit": 3,
    })
    qtbot.addWidget(view)
    view.set_board(board)
    assert view.history_combo.count() == 1

    view.history_combo.setCurrentIndex(0)
    with _confirm_yes():
        view.delete_history_button.click()

    assert view.history_combo.count() == 0
    assert config_repo.list_for_board(board.id) == []
    db.close()


def test_delete_history_config_blocked_when_used_by_a_test_session(qtbot, tmp_path: Path) -> None:
    db = Database(tmp_path / "del_config_blocked.db")
    db.connect()
    board_repo = BoardRepository(db)
    operator_repo = OperatorRepository(db)
    config_repo = TestParameterConfigRepository(db)
    board = board_repo.get_or_create("PCB-1", "PN-1", "A")
    operator = operator_repo.get_or_create("Op")
    config = config_repo.save(
        TestParameterConfig(
            id=None, board_id=board.id, name="Usado de verdade", nominal_voltage=5.0,
            voltage_min=4.5, voltage_max=5.5, current_max=1.0, test_duration_s=60.0,
            power_sequence=[],
        )
    )
    TestSessionRepository(db).create(
        TestSession(
            id=None, board_id=board.id, serial_number="SN-1", operator_id=operator.id,
            test_parameter_config_id=config.id, config_snapshot_json="{}",
            production_order=None, observations=None, status=TestSessionStatus.COMPLETED,
        )
    )
    view = TestParametersView(config_repo, {
        "polling_rate_hz": 1.0, "stabilization_timeout_s": 5.0,
        "stabilization_tolerance_v": 0.05, "monitoring_consecutive_failures_limit": 3,
    })
    qtbot.addWidget(view)
    view.set_board(board)
    view.history_combo.setCurrentIndex(0)

    with _confirm_yes(), patch.object(QtWidgets.QMessageBox, "warning") as mock_warning:
        view.delete_history_button.click()

    mock_warning.assert_called_once()
    assert view.history_combo.count() == 1  # não foi removido
    db.close()
