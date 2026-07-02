"""Reprodução do "SCPI error -222: Data out of range" relatado em campo ao
ligar a saída manual (e no meio de um ensaio multi-step) numa fonte E3634A.

"Simular antes de codar" (mesmo pedido que gerou `test_serial_simulation.py`):
a causa raiz é que o driver nunca mandava `VOLTage:RANGe` — a fonte ficava na
faixa que já estivesse (painel frontal ou sessão anterior), e um setpoint que
cabe numa faixa MAIOR falhava por não caber na faixa ATIVA. Os testes abaixo
primeiro reproduzem o defeito contra `SimulatedE3634A` (sem gerenciamento de
faixa) e depois validam que `PowerSupplyE363x` com `ranges` configurado
resolve, antes de confiar a correção ao hardware real.
"""
from __future__ import annotations

import pytest

from config import ReconnectionConfig, SerialConfig, VoltageRange
from drivers.exceptions import InstrumentRangeOutOfBoundsError, ScpiInstrumentFaultError
from hardware.power_supply import PowerSupplyE363x
from tests.e363x_simulator import SimulatedE3634A

_LOW = VoltageRange(name="LOW", max_voltage=25.0, max_current=7.0)
_HIGH = VoltageRange(name="HIGH", max_voltage=50.0, max_current=4.0)


def _serial_config(**overrides) -> SerialConfig:
    defaults = dict(
        port="COM-SIM",
        vid=None,
        pid=None,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=2,
        timeout_s=0.1,
        write_timeout_s=0.1,
        force_dtr_high=True,
        force_rts_high=True,
        rtscts=False,
        dsrdtr=False,
        port_settle_s=0.0,  # testes não esperam o atraso de acomodação real
    )
    defaults.update(overrides)
    return SerialConfig(**defaults)


def _reconnection() -> ReconnectionConfig:
    return ReconnectionConfig(
        max_retries=1, backoff_base_s=0.0, backoff_multiplier=1.0, heartbeat_interval_s=5.0
    )


def _patch_serial(mocker, **sim_kwargs) -> dict[str, SimulatedE3634A]:
    holder: dict[str, SimulatedE3634A] = {}

    def factory(**serial_kwargs):
        sim = SimulatedE3634A(**{**serial_kwargs, **sim_kwargs})
        holder["sim"] = sim
        return sim

    mocker.patch("drivers.serial_driver.serial.Serial", side_effect=factory)
    return holder


# -- Reprodução do defeito de campo ------------------------------------------


def test_apply_above_active_range_fails_without_range_management(mocker) -> None:
    """26 V cabe na faixa HIGH (50V/4A) mas NÃO na LOW (25V/7A), que é a
    ativa por padrão na fonte simulada — reproduz exatamente o sintoma
    relatado (Saída manual 26V/1A -> -222) quando o driver não gerencia
    faixa nenhuma (ranges=() — comportamento anterior a esta correção)."""
    _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection())  # sem ranges
    instrument.connect()

    with pytest.raises(ScpiInstrumentFaultError) as excinfo:
        instrument.apply(26.0, 1.0)
    assert excinfo.value.code == -222


# -- Correção: seleção automática de faixa -----------------------------------


def test_apply_switches_to_a_wider_range_automatically(mocker) -> None:
    holder = _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_LOW, _HIGH))
    instrument.connect()

    instrument.apply(26.0, 1.0)  # não deve levantar mais

    assert holder["sim"].range_switches == ["HIGH"]
    assert holder["sim"]._active_range == "HIGH"


def test_apply_does_not_switch_range_when_current_one_already_fits(mocker) -> None:
    """Sem necessidade de troca, nenhum VOLTage:RANGe extra é mandado —
    troca de faixa é potencialmente perturbadora (ver teste de warning
    abaixo) e não deve ocorrer sem necessidade. A 1a aplicação da sessão
    sempre seleciona a faixa explicitamente (não confia em estado herdado
    de fora) -- o que se testa aqui é a 2a chamada em diante."""
    holder = _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_LOW, _HIGH))
    instrument.connect()

    instrument.apply(5.0, 1.0)
    assert holder["sim"].range_switches == ["LOW"]  # 1a chamada: seleção explícita

    instrument.apply(6.0, 1.0)  # ainda cabe em LOW -- não deve repetir a troca

    assert holder["sim"].range_switches == ["LOW"]


def test_apply_prefers_the_narrower_range_that_fits(mocker) -> None:
    """5V/1A cabe nas duas faixas -- deve escolher a mais 'justa' (LOW), não
    a HIGH, mesmo partindo de HIGH ativa (mais resolução pro operador)."""
    holder = _patch_serial(mocker, active_range="HIGH")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_HIGH, _LOW))
    instrument.connect()

    instrument.apply(5.0, 1.0)

    assert holder["sim"].range_switches == ["LOW"]


def test_apply_raises_actionable_error_when_no_range_fits(mocker) -> None:
    """60V não cabe em LOW (25V) nem HIGH (50V) -- erro do CLIENTE, acionável,
    antes de qualquer I/O, em vez do -222 genérico da fonte."""
    holder = _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_LOW, _HIGH))
    instrument.connect()

    with pytest.raises(InstrumentRangeOutOfBoundsError) as excinfo:
        instrument.apply(60.0, 1.0)

    assert "60.00" in str(excinfo.value)
    assert holder["sim"].range_switches == []  # nenhum VOLTage:RANGe chegou a ser mandado


def test_reconnect_forces_explicit_range_reselection(mocker) -> None:
    """Não confia que a faixa continua a mesma entre sessões: mesmo pedindo
    o MESMO setpoint de novo após reconectar, a faixa é reafirmada
    explicitamente -- cobre ajuste manual do operador no painel frontal ou
    estado inconsistente carregado de uma sessão anterior."""
    holder = _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_LOW, _HIGH))
    instrument.connect()
    instrument.apply(26.0, 1.0)

    instrument.disconnect()
    instrument.connect()  # holder["sim"] passa a apontar pro simulador da 2a conexão
    instrument.apply(26.0, 1.0)

    assert holder["sim"].range_switches == ["HIGH"]


def test_switching_range_with_output_on_logs_a_warning(mocker, caplog) -> None:
    """Trocar de faixa com a saída ligada pode cortar a tensão momentaneamente
    na placa sob teste -- cenário típico de sequência multi-step que atravessa
    LOW e HIGH -- então precisa ficar visível no log, não silencioso."""
    import logging

    _patch_serial(mocker, active_range="LOW")
    instrument = PowerSupplyE363x(_serial_config(), _reconnection(), ranges=(_LOW, _HIGH))
    instrument.connect()
    instrument.apply(5.0, 1.0)
    instrument.output_on()

    with caplog.at_level(logging.WARNING, logger="app"):
        instrument.apply(26.0, 1.0)  # passo seguinte de um ensaio, saída já ligada

    assert any("saída ligada" in rec.message.lower() for rec in caplog.records)
