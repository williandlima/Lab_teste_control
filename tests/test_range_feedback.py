"""Testa a parte PURA de gui/widgets/range_feedback.py (sem Qt/offscreen).

A parte visual (cor/tooltip em QDoubleSpinBox/QTableWidgetItem) é coberta
pelos testes com marker 'gui' em test_gui_smoke.py / test_manual_output_range.py
/ test_test_parameters_view_range.py -- aqui só a lógica de classificação,
que precisa rodar em qualquer CI mesmo sem display.
"""
from __future__ import annotations

from config import VoltageRange
from gui.widgets.range_feedback import RangeFitState, evaluate_range_fit

_LOW = VoltageRange(name="LOW", max_voltage=25.0, max_current=7.0)
_HIGH = VoltageRange(name="HIGH", max_voltage=50.0, max_current=4.0)
_RANGES = (_LOW, _HIGH)


def test_no_ranges_configured_is_always_ok() -> None:
    result = evaluate_range_fit(999.0, 999.0, ())
    assert result.state is RangeFitState.OK
    assert result.message == ""


def test_fits_low_range_automatic_mode_is_ok() -> None:
    assert evaluate_range_fit(5.0, 1.0, _RANGES).state is RangeFitState.OK


def test_fits_high_but_not_low_automatic_mode_is_ok() -> None:
    """26V não cabe em LOW mas cabe em HIGH -- seleção automática cobre
    isso, então não é motivo de aviso (é exatamente o caso do fix da
    E3634A: 26V/1A deve ficar OK no modo automático)."""
    result = evaluate_range_fit(26.0, 1.0, _RANGES)
    assert result.state is RangeFitState.OK


def test_does_not_fit_any_range_automatic_mode_is_out_of_all() -> None:
    result = evaluate_range_fit(60.0, 1.0, _RANGES)
    assert result.state is RangeFitState.OUT_OF_ALL_RANGES
    assert "60.00" in result.message


def test_forced_range_that_fits_is_ok() -> None:
    result = evaluate_range_fit(5.0, 1.0, _RANGES, forced_range_name="HIGH")
    assert result.state is RangeFitState.OK


def test_forced_low_range_with_value_that_only_fits_high_warns() -> None:
    result = evaluate_range_fit(26.0, 1.0, _RANGES, forced_range_name="LOW")
    assert result.state is RangeFitState.OUT_OF_FORCED_RANGE
    assert "LOW" in result.message
    assert "HIGH" in result.message


def test_forced_range_with_value_that_fits_nothing_is_out_of_all() -> None:
    result = evaluate_range_fit(60.0, 1.0, _RANGES, forced_range_name="LOW")
    assert result.state is RangeFitState.OUT_OF_ALL_RANGES


def test_forced_range_name_that_does_not_exist_falls_back_to_fitting_check() -> None:
    """Nome de faixa forçada inexistente ('MEDIUM') não deve explodir --
    trata como 'não cabe na forçada' e sugere a que realmente serve."""
    result = evaluate_range_fit(5.0, 1.0, _RANGES, forced_range_name="MEDIUM")
    assert result.state is RangeFitState.OUT_OF_FORCED_RANGE
    assert "LOW" in result.message
