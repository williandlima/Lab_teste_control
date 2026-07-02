"""Testes da máquina de estados com instrumento mockado (sem hardware real).

Cobre o caminho feliz e as principais políticas de retry/abort/failsafe do
diagrama aprovado: falha de comunicação, falha de configuração, abort
manual durante o monitoramento, e a garantia de que output_off() é sempre
chamado antes de liberar a avaliação manual.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.sampling_buffer import SamplingBuffer
from core.state_machine import TestRunConfig, TestState, TestStateMachine
from drivers.exceptions import SerialTimeoutError
from hardware.power_supply import PowerSupplyE363x


def _make_config(**overrides) -> TestRunConfig:
    defaults = dict(
        nominal_voltage=12.0,
        voltage_min=11.5,
        voltage_max=12.5,
        current_max=2.0,
        test_duration_s=0.05,
        power_sequence=[],
        polling_rate_hz=50.0,
        stabilization_timeout_s=1.0,
        stabilization_tolerance_v=0.05,
        monitoring_consecutive_failures_limit=3,
    )
    defaults.update(overrides)
    return TestRunConfig(**defaults)


def _make_mock_instrument() -> MagicMock:
    instrument = MagicMock(spec=PowerSupplyE363x)
    instrument.connect.return_value = None
    instrument.heartbeat.return_value = True
    instrument.measure_voltage.return_value = 12.0
    instrument.measure_current.return_value = 1.0
    return instrument


def _make_buffer(flushed_batches: list) -> SamplingBuffer:
    return SamplingBuffer(
        live_buffer_maxlen=1000, batch_size=1000, batch_interval_s=999, on_flush=flushed_batches.append
    )


def test_happy_path_completes_and_shuts_down_output() -> None:
    instrument = _make_mock_instrument()
    flushed_batches: list = []
    buffer = _make_buffer(flushed_batches)
    events: list[tuple[str, str]] = []
    sm = TestStateMachine(
        instrument, buffer, _make_config(), on_event=lambda lvl, msg: events.append((lvl, msg))
    )

    result = sm.run()

    assert result == TestState.COMPLETED
    assert sm.state == TestState.AWAITING_MANUAL_EVALUATION
    instrument.output_on.assert_called_once()
    instrument.output_off.assert_called_once()
    assert len(flushed_batches) == 1
    assert len(flushed_batches[0]) > 0
    assert not any(level == "ERROR" for level, _ in events)


def test_capture_interval_records_fewer_than_displayed() -> None:
    """Display em alta frequência, gravação throttled (evita overdata)."""
    instrument = _make_mock_instrument()
    flushed_batches: list = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100000, batch_size=100000, batch_interval_s=999,
        on_flush=flushed_batches.append,
    )
    displayed: list = []
    config = _make_config(test_duration_s=0.3, polling_rate_hz=100.0, capture_interval_s=0.1)
    sm = TestStateMachine(instrument, buffer, config, on_sample=lambda s: displayed.append(s))

    result = sm.run()

    captured = flushed_batches[0] if flushed_batches else []
    assert result == TestState.COMPLETED
    assert len(captured) >= 1
    assert len(displayed) > len(captured)  # monitorou muito mais do que gravou


def test_capture_interval_zero_records_every_sample() -> None:
    instrument = _make_mock_instrument()
    flushed_batches: list = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100000, batch_size=100000, batch_interval_s=999,
        on_flush=flushed_batches.append,
    )
    displayed: list = []
    config = _make_config(test_duration_s=0.2, polling_rate_hz=100.0, capture_interval_s=0.0)
    sm = TestStateMachine(instrument, buffer, config, on_sample=lambda s: displayed.append(s))

    sm.run()

    assert len(flushed_batches[0]) == len(displayed)  # grava todas quando intervalo=0


def test_initialize_failure_leads_to_comm_error_and_still_shuts_down() -> None:
    instrument = _make_mock_instrument()
    instrument.connect.side_effect = SerialTimeoutError("sem resposta")
    instrument.reconnect.return_value = False
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config())

    result = sm.run()

    assert result == TestState.COMM_ERROR
    assert sm.termination_reason == TestState.COMM_ERROR
    instrument.output_off.assert_called_once()
    instrument.output_on.assert_not_called()


def test_configure_source_failure_leads_to_faulted_with_failsafe_shutdown() -> None:
    instrument = _make_mock_instrument()
    instrument.set_overvoltage_protection.side_effect = SerialTimeoutError("erro de protecao")
    buffer = _make_buffer([])
    config = _make_config(ovp_level_v=13.0)
    sm = TestStateMachine(instrument, buffer, config)

    result = sm.run()

    assert result == TestState.FAULTED
    instrument.output_off.assert_called_once()
    instrument.output_on.assert_not_called()


def test_configure_source_skips_protection_by_default() -> None:
    """ovp_level_v/ocp_level_a = 0 (default): não configura nada — a fonte mantém
    sua própria proteção e ela não atua durante o ensaio (decisão do operador)."""
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    config = _make_config()
    sm = TestStateMachine(instrument, buffer, config)

    result = sm.run()

    assert result == TestState.COMPLETED
    instrument.set_overvoltage_protection.assert_not_called()
    instrument.set_overcurrent_protection.assert_not_called()


def test_configure_source_arms_protection_at_operator_defined_levels() -> None:
    """Quando o operador define OVP/OCP, a fonte é armada exatamente nesse valor
    (sem cálculo automático — já causou disparo indevido e SCPI -222 Data out
    of range quando a margem ultrapassava a faixa aceita pelo instrumento)."""
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    config = _make_config(ovp_level_v=13.5, ocp_level_a=2.2)
    sm = TestStateMachine(instrument, buffer, config)

    sm.run()

    instrument.set_overvoltage_protection.assert_called_once_with(13.5, clear_latch=False)
    instrument.set_overcurrent_protection.assert_called_once_with(2.2, clear_latch=False)


def test_monitor_resyncs_buffer_after_read_failure() -> None:
    """Após falha de leitura, limpa o buffer para não casar resposta com comando errado."""
    instrument = _make_mock_instrument()
    instrument.measure_current.side_effect = [SerialTimeoutError("timeout")] + [1.0] * 1000
    buffer = _make_buffer([])
    config = _make_config(test_duration_s=0.05, polling_rate_hz=100.0)
    sm = TestStateMachine(instrument, buffer, config)

    sm.run()

    assert instrument.reset_io_buffers.called


def test_stabilization_timeout_proceeds_to_monitoring_not_faulted() -> None:
    """Não estabilizar não aborta: segue monitorando para o operador ver as leituras."""
    instrument = _make_mock_instrument()
    instrument.measure_voltage.return_value = 5.0  # nunca atinge o alvo (12.0)
    flushed_batches: list = []
    buffer = _make_buffer(flushed_batches)
    events: list[tuple[str, str]] = []
    config = _make_config(stabilization_timeout_s=0.1, test_duration_s=0.1, polling_rate_hz=100.0)
    sm = TestStateMachine(instrument, buffer, config, on_event=lambda lvl, msg: events.append((lvl, msg)))

    result = sm.run()

    assert result == TestState.COMPLETED
    assert any(lvl == "WARNING" and "estabiliz" in msg.lower() for lvl, msg in events)
    assert len(flushed_batches[0]) > 0  # houve leituras registradas no monitoramento
    instrument.output_off.assert_called_once()


def test_apply_voltage_failure_has_no_retry() -> None:
    instrument = _make_mock_instrument()
    instrument.apply.side_effect = SerialTimeoutError("falha ao aplicar")
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config())

    result = sm.run()

    assert result == TestState.FAULTED
    assert instrument.apply.call_count == 1
    instrument.output_off.assert_called_once()


def test_abort_during_monitoring_leads_to_aborted() -> None:
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    config = _make_config(test_duration_s=5.0)
    sm = TestStateMachine(instrument, buffer, config)

    call_count = {"n": 0}

    def measure_voltage_then_abort() -> float:
        call_count["n"] += 1
        if call_count["n"] == 2:
            sm.request_abort()
        return 12.0

    instrument.measure_voltage.side_effect = measure_voltage_then_abort

    result = sm.run()

    assert result == TestState.ABORTED
    instrument.output_off.assert_called_once()


def test_monitoring_aborts_after_consecutive_read_failures() -> None:
    instrument = _make_mock_instrument()
    instrument.measure_voltage.side_effect = SerialTimeoutError("timeout de leitura")
    buffer = _make_buffer([])
    config = _make_config(monitoring_consecutive_failures_limit=2, test_duration_s=5.0)
    sm = TestStateMachine(instrument, buffer, config)

    result = sm.run()

    assert result == TestState.COMM_ERROR
    instrument.output_off.assert_called_once()


def test_mark_evaluated_transitions_to_completed_after_run() -> None:
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config())
    sm.run()

    sm.mark_evaluated()

    assert sm.state == TestState.COMPLETED


def test_mark_evaluated_raises_before_test_finishes() -> None:
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config())

    with pytest.raises(RuntimeError):
        sm.mark_evaluated()


def test_configure_source_forwards_range_mode_to_the_instrument() -> None:
    """O operador pode travar a faixa V/A no preset de parâmetros (ver
    TestParametersView) -- _configure_source precisa repassar essa escolha
    para o driver ANTES do primeiro apply(), a cada (re)configuração."""
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config(range_mode="HIGH"))

    sm.run()

    instrument.set_forced_range.assert_any_call("HIGH")


def test_configure_source_forwards_automatic_range_mode_by_default() -> None:
    instrument = _make_mock_instrument()
    buffer = _make_buffer([])
    sm = TestStateMachine(instrument, buffer, _make_config())  # range_mode não informado = None

    sm.run()

    instrument.set_forced_range.assert_any_call(None)
