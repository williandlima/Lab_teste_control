"""Testes do transporte serial: resolução de porta e reconexão com backoff.

Não abre portas reais — `connect()` é stubado nos testes de reconexão, e os
testes de leitura/escrita usam um objeto serial.Serial falso injetado
diretamente em `_serial` (evita depender de hardware/porta real).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config import SerialConfig
from drivers.exceptions import SerialConnectionError, SerialTimeoutError
from drivers.serial_driver import SerialTransport, find_port_by_vid_pid


def _make_config(**overrides) -> SerialConfig:
    defaults = dict(
        port=None,
        vid=None,
        pid=None,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=2,
        timeout_s=2.0,
        write_timeout_s=2.0,
        force_dtr_high=True,
    )
    defaults.update(overrides)
    return SerialConfig(**defaults)


def test_resolve_port_uses_fixed_port_when_configured() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    assert transport.resolve_port() == "COM3"


def test_resolve_port_uses_vid_pid_when_no_fixed_port(mocker) -> None:
    mocker.patch("drivers.serial_driver.find_port_by_vid_pid", return_value="COM7")
    transport = SerialTransport(_make_config(vid=0x0403, pid=0x6001))
    assert transport.resolve_port() == "COM7"


def test_resolve_port_raises_when_nothing_found(mocker) -> None:
    mocker.patch("drivers.serial_driver.find_port_by_vid_pid", return_value=None)
    transport = SerialTransport(_make_config(vid=0x0403, pid=0x6001))
    with pytest.raises(SerialConnectionError):
        transport.resolve_port()


def test_find_port_by_vid_pid_matches_descriptor(mocker) -> None:
    fake_port = MagicMock(device="COM5", vid=0x0403, pid=0x6001)
    mocker.patch("serial.tools.list_ports.comports", return_value=[fake_port])
    assert find_port_by_vid_pid(0x0403, 0x6001) == "COM5"


def test_write_line_requires_open_connection() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    with pytest.raises(SerialConnectionError):
        transport.write_line("*IDN?")


def test_read_line_requires_open_connection() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    with pytest.raises(SerialConnectionError):
        transport.read_line()


def test_write_line_sends_lf_terminated_payload() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    transport._serial = MagicMock(is_open=True)
    transport.write_line("*IDN?")
    transport._serial.write.assert_called_once_with(b"*IDN?\n")


def test_read_line_raises_timeout_on_empty_response() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    transport._serial = MagicMock(is_open=True)
    transport._serial.readline.return_value = b""
    with pytest.raises(SerialTimeoutError):
        transport.read_line()


def test_read_line_decodes_and_strips_response() -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    transport._serial = MagicMock(is_open=True)
    transport._serial.readline.return_value = b"12.0034\n"
    assert transport.read_line() == "12.0034"


def test_reconnect_with_backoff_succeeds_after_retries(mocker) -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    mocker.patch.object(transport, "disconnect")
    mocker.patch("time.sleep")
    connect_mock = mocker.patch.object(
        transport, "connect", side_effect=[SerialConnectionError("boom"), None]
    )
    assert transport.reconnect_with_backoff(max_retries=3, backoff_base_s=1.0, multiplier=2.0) is True
    assert connect_mock.call_count == 2


def test_reconnect_with_backoff_gives_up_after_max_retries(mocker) -> None:
    transport = SerialTransport(_make_config(port="COM3"))
    mocker.patch.object(transport, "disconnect")
    mocker.patch("time.sleep")
    mocker.patch.object(transport, "connect", side_effect=SerialConnectionError("boom"))
    assert transport.reconnect_with_backoff(max_retries=3, backoff_base_s=1.0, multiplier=2.0) is False
