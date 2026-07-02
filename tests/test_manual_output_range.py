"""Testes 'gui' (offscreen) da seleção de faixa e aviso visual em tempo real
na Saída manual — reproduz o pedido do operador: poder escolher a faixa e
ser avisado (cor/tooltip) de um limite fora da faixa ANTES de clicar em
"Ligar saída", em vez de só descobrir com o -222 do instrumento.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

pytestmark = pytest.mark.gui

from config import ReconnectionConfig, SerialConfig, VoltageRange
from gui.manual_output_dialog import ManualOutputDialog
from gui.widgets.range_feedback import RangeFitState
from hardware.power_supply import PowerSupplyE363x

_LOW = VoltageRange(name="LOW", max_voltage=25.0, max_current=7.0)
_HIGH = VoltageRange(name="HIGH", max_voltage=50.0, max_current=4.0)


def _serial_config() -> SerialConfig:
    return SerialConfig(
        port="COM-SIM", vid=None, pid=None, baudrate=9600, bytesize=8, parity="N",
        stopbits=2, timeout_s=0.1, write_timeout_s=0.1, force_dtr_high=True,
        force_rts_high=True, rtscts=False, dsrdtr=False, port_settle_s=0.0,
    )


def _reconnection() -> ReconnectionConfig:
    return ReconnectionConfig(max_retries=1, backoff_base_s=0.0, backoff_multiplier=1.0, heartbeat_interval_s=5.0)


def _dialog(qtbot, ranges=(_LOW, _HIGH), simulate=True):
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=ranges)
    dialog = ManualOutputDialog(
        instrument, simulate=simulate, port="COM-SIM", default_voltage=5.0, default_current=1.0
    )
    qtbot.addWidget(dialog)
    dialog.show()  # isVisible() só reflete a hierarquia real se o topo foi mostrado
    return dialog


def test_range_combo_lists_automatic_plus_each_configured_range(qtbot) -> None:
    dialog = _dialog(qtbot)
    labels = [dialog.range_combo.itemText(i) for i in range(dialog.range_combo.count())]
    assert labels[0].startswith("Automática")
    assert dialog.range_combo.itemData(0) is None
    assert any("LOW" in label for label in labels)
    assert any("HIGH" in label for label in labels)


def test_value_that_fits_automatic_mode_shows_no_warning(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.voltage_spin.setValue(26.0)  # não cabe em LOW mas cabe em HIGH -- automático resolve
    dialog.current_spin.setValue(1.0)
    assert dialog._range_ok is True
    assert dialog.range_warning_label.isVisible() is False
    assert dialog.on_button.isEnabled() is True


def test_value_out_of_all_ranges_disables_turn_on_and_shows_warning(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.voltage_spin.setValue(5.0)
    dialog.current_spin.setValue(10.0)  # excede LOW (7A) e HIGH (4A) -- não cabe em nenhuma
    assert dialog._range_ok is False
    assert dialog.range_warning_label.isVisible() is True
    assert "10.000" in dialog.range_warning_label.text()
    assert dialog.on_button.isEnabled() is False
    assert "border" in dialog.current_spin.styleSheet()


def test_forcing_low_range_with_high_only_value_warns_and_blocks(qtbot) -> None:
    dialog = _dialog(qtbot)
    low_index = next(
        i for i in range(dialog.range_combo.count()) if dialog.range_combo.itemData(i) == "LOW"
    )
    dialog.range_combo.setCurrentIndex(low_index)
    dialog.voltage_spin.setValue(26.0)  # só cabe em HIGH, mas LOW foi forçada
    dialog.current_spin.setValue(1.0)

    assert dialog._range_ok is False
    assert dialog.on_button.isEnabled() is False
    assert "HIGH" in dialog.range_warning_label.text()  # sugere a faixa que serviria


def test_fixing_the_value_after_a_warning_re_enables_turn_on(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.current_spin.setValue(10.0)  # excede LOW (7A) e HIGH (4A)
    assert dialog.on_button.isEnabled() is False

    dialog.current_spin.setValue(1.0)  # corrige para um valor válido

    assert dialog._range_ok is True
    assert dialog.on_button.isEnabled() is True
    assert dialog.range_warning_label.isVisible() is False


def test_no_ranges_configured_disables_combo_and_never_warns(qtbot) -> None:
    dialog = _dialog(qtbot, ranges=())
    assert dialog.range_combo.isEnabled() is False
    dialog.voltage_spin.setValue(999.0)  # qualquer valor -- gerenciamento desligado
    assert dialog._range_ok is True
    assert dialog.on_button.isEnabled() is True


def test_turn_on_with_forced_range_sends_it_to_the_instrument(qtbot, mocker) -> None:
    """Ponta-a-ponta: escolher uma faixa no combo e clicar em Ligar deve
    chamar set_forced_range() com o nome escolhido antes do apply()."""
    from unittest.mock import patch

    from PySide6 import QtWidgets

    from tests.e363x_simulator import SimulatedE3634A

    holder = {}

    def factory(**kwargs):
        sim = SimulatedE3634A(active_range="LOW", **kwargs)
        holder["sim"] = sim
        return sim

    mocker.patch("drivers.serial_driver.serial.Serial", side_effect=factory)
    dialog = _dialog(qtbot, simulate=False)
    high_index = next(
        i for i in range(dialog.range_combo.count()) if dialog.range_combo.itemData(i) == "HIGH"
    )
    dialog.range_combo.setCurrentIndex(high_index)
    dialog.voltage_spin.setValue(5.0)  # caberia em LOW, mas HIGH foi forçada
    dialog.current_spin.setValue(1.0)

    with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.StandardButton.Yes):
        dialog.on_button.click()
        for _ in range(200):
            qtbot.wait(10)
            if not dialog._busy:
                break

    assert dialog._output_on is True
    assert holder["sim"].range_switches == ["HIGH"]  # forçada, não a mais "justa" (LOW)
    dialog._shutdown()
