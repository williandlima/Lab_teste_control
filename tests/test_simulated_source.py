"""Testa o modo SIMULAÇÃO (fonte saudável) usado quando não há hardware.

Garante que, com `serial.simulate=True`, o app roda o fluxo completo do ensaio
até COMPLETED e coleta amostras de tensão/corrente próximas ao setpoint — o
oposto do sintoma "a tela abre e já encerra o teste" (que ocorria por falta de
fonte conectada).
"""
from __future__ import annotations

from config import ReconnectionConfig, SerialConfig
from core.sampling_buffer import SamplingBuffer
from core.state_machine import TestRunConfig, TestState, TestStateMachine
from database.models import PowerStep
from drivers.simulated_serial import SimulatedE363xSerial
from hardware.power_supply import PowerSupplyE363x


def _serial_config() -> SerialConfig:
    return SerialConfig(
        port=None, vid=None, pid=None, baudrate=9600, bytesize=8, parity="N",
        stopbits=2, timeout_s=2.0, write_timeout_s=2.0, force_dtr_high=True,
        force_rts_high=True, rtscts=False, dsrdtr=False, simulate=True,
    )


def test_simulated_serial_responds_to_idn_and_measures() -> None:
    sim = SimulatedE363xSerial(seed=1)
    sim.write(b"*IDN?\n")
    assert b"," in sim.readline()  # identidade plausível (com vírgulas)

    sim.write(b"SYSTem:REMote\n")
    sim.write(b"APPLy 5.0000,1.0000\n")
    sim.write(b"OUTPut:STATe ON\n")
    sim.write(b"MEASure:VOLTage:DC?\n")
    voltage = float(sim.readline())
    sim.write(b"MEASure:CURRent:DC?\n")
    current = float(sim.readline())

    assert abs(voltage - 5.0) <= 0.05
    assert 0.0 <= current <= 1.0


def test_simulated_serial_output_off_reads_near_zero() -> None:
    sim = SimulatedE363xSerial(seed=2)
    sim.write(b"APPLy 5.0,1.0\n")
    sim.write(b"MEASure:VOLTage:DC?\n")
    assert float(sim.readline()) < 0.1  # saída desligada -> ~0 V


def test_transport_runtime_simulate_override() -> None:
    """Botão 'Simulação' do cabeçalho liga a fonte virtual mesmo com config=False."""
    from drivers.serial_driver import SerialTransport

    config = _serial_config()
    object.__setattr__(config, "simulate", False)  # config desliga...
    transport = SerialTransport(config)
    transport.set_simulate(True)  # ...mas o operador liga em tempo de execução

    transport.connect()

    assert transport.is_open
    assert isinstance(transport._serial, SimulatedE363xSerial)
    transport.disconnect()


def test_transport_connect_is_idempotent_and_buffers_resettable() -> None:
    """Reconectar não vaza handle; reset_io_buffers é seguro aberto e fechado."""
    from drivers.serial_driver import SerialTransport

    transport = SerialTransport(_serial_config())  # simulate=True
    transport.connect()
    assert transport.is_open
    transport.connect()  # idempotente: fecha o anterior e reabre, sem erro
    assert transport.is_open

    transport.reset_io_buffers()  # com porta aberta: ok
    transport.disconnect()
    transport.reset_io_buffers()  # com porta fechada: no-op, sem exceção


def test_state_machine_completes_in_simulation_mode() -> None:
    instrument = PowerSupplyE363x(_serial_config(), ReconnectionConfig(
        max_retries=3, backoff_base_s=0.1, backoff_multiplier=2.0, heartbeat_interval_s=5.0
    ))
    samples = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100, batch_size=10, batch_interval_s=1.0, on_flush=lambda s: None
    )
    config = TestRunConfig(
        nominal_voltage=5.0, voltage_min=4.5, voltage_max=5.5, current_max=1.0,
        test_duration_s=1.0, power_sequence=[PowerStep(5.0, 1.0, 1.0)],
        polling_rate_hz=20.0, stabilization_timeout_s=3.0, stabilization_tolerance_v=0.05,
        monitoring_consecutive_failures_limit=5,
    )
    sm = TestStateMachine(instrument, buffer, config, on_sample=lambda s: samples.append(s))

    result = sm.run()

    assert result == TestState.COMPLETED
    assert len(samples) > 0
    assert all(4.5 <= s.voltage <= 5.5 for s in samples)
    # Rastreabilidade: a identidade (*IDN?) foi capturada durante a conexão.
    assert instrument.last_identity is not None
    assert "," in instrument.last_identity
