"""Reprodução dos sintomas de campo do RS-232 contra um simulador da E3631A.

"Simular antes de codar" (pedido da revisão sênior): aqui os dois sintomas
relatados — timeout e apito constante — são reproduzidos de forma determinística
contra `tests/e363x_simulator.py`, e validamos que a nova sonda diagnóstica
(`SerialTransport.probe_identity` / `PowerSupplyE363x.test_connection`)
identifica a causa em vez de só estourar um erro genérico.
"""
from __future__ import annotations

import pytest

from config import ReconnectionConfig, SerialConfig
from drivers.exceptions import ScpiFramingError, SerialTimeoutError
from drivers.serial_driver import SerialTransport
from hardware.power_supply import PowerSupplyE363x
from tests.e363x_simulator import SimulatedE3631A


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
    )
    defaults.update(overrides)
    return SerialConfig(**defaults)


def _patch_serial(mocker, **sim_kwargs) -> dict[str, SimulatedE3631A]:
    """Faz `serial.Serial(...)` devolver um simulador com o cenário pedido.

    Devolve um dict que, após `connect()`, guarda em ["sim"] a instância criada,
    para o teste poder inspecionar beep_count/error_queue.
    """
    holder: dict[str, SimulatedE3631A] = {}

    def factory(**serial_kwargs):
        sim = SimulatedE3631A(**{**serial_kwargs, **sim_kwargs})
        holder["sim"] = sim
        return sim

    mocker.patch("drivers.serial_driver.serial.Serial", side_effect=factory)
    return holder


# -- Sintoma 1: timeout (cabo de 3 fios sem DSR) ----------------------------


def test_three_wire_cable_without_dsr_times_out_with_actionable_message(mocker) -> None:
    _patch_serial(mocker, dsr_wired=False)
    transport = SerialTransport(_serial_config())
    transport.connect()

    with pytest.raises(SerialTimeoutError) as excinfo:
        transport.probe_identity()

    # A mensagem precisa apontar o operador para cabo/handshake, não um traceback cru.
    message = str(excinfo.value).lower()
    assert "timeout" in message
    assert "dtr" in message and "dsr" in message


def test_power_supply_test_connection_diagnoses_timeout(mocker) -> None:
    _patch_serial(mocker, dsr_wired=False)
    instrument = PowerSupplyE363x(_serial_config(), _reconnection())

    with pytest.raises(SerialTimeoutError):
        instrument.test_connection()
    # test_connection deve ter fechado a porta mesmo em falha.
    assert not instrument.is_connected


# -- Sintoma 2: apito constante (parâmetros divergentes -> framing) ----------


def test_parameter_mismatch_raises_framing_not_timeout(mocker) -> None:
    holder = _patch_serial(mocker, dsr_wired=True)
    # Baudrate divergente do painel (9600) -> todo comando vira lixo de framing.
    transport = SerialTransport(_serial_config(baudrate=4800))
    transport.connect()

    with pytest.raises(ScpiFramingError) as excinfo:
        transport.probe_identity()

    assert "framing" in str(excinfo.value).lower()


def test_probe_does_not_storm_the_beeper(mocker) -> None:
    """A sonda manda só *CLS + *IDN?: no pior caso 2 erros, nunca um bip por comando."""
    holder = _patch_serial(mocker, dsr_wired=True)
    transport = SerialTransport(_serial_config(baudrate=4800))
    transport.connect()
    with pytest.raises(ScpiFramingError):
        transport.probe_identity()

    sim = holder["sim"]
    # *CLS e *IDN? = no máximo 2 bips. O comportamento antigo (REMote+CLS+
    # ERRor?+IDN? em sequência) geraria mais — esta asserção trava a regressão.
    assert sim.beep_count <= 2


# -- Caminho feliz: identificação correta -----------------------------------


def test_healthy_link_identifies_instrument(mocker) -> None:
    _patch_serial(mocker, dsr_wired=True)
    instrument = PowerSupplyE363x(_serial_config(), _reconnection())

    identity = instrument.test_connection()

    assert "E3631A" in identity
    assert not instrument.is_connected  # test_connection não deixa a porta aberta


def test_operator_chosen_port_overrides_config(mocker) -> None:
    _patch_serial(mocker, dsr_wired=True)
    transport = SerialTransport(_serial_config(port="COM1"))
    transport.set_port_override("COM9")
    assert transport.resolve_port() == "COM9"
    transport.set_port_override(None)
    assert transport.resolve_port() == "COM1"


def _reconnection() -> ReconnectionConfig:
    return ReconnectionConfig(
        max_retries=1, backoff_base_s=0.0, backoff_multiplier=1.0, heartbeat_interval_s=5.0
    )
