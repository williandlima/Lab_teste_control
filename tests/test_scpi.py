"""Testes do parser/protocolo SCPI genérico, sem hardware real."""
from __future__ import annotations

import pytest

from drivers.exceptions import ScpiError, ScpiFramingError, ScpiInstrumentFaultError
from drivers.scpi import ScpiProtocol


class FakeTransport:
    """Dublê de SerialTransport: fila de respostas programada pelo teste."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.written: list[str] = []

    def write_line(self, command: str) -> None:
        self.written.append(command)

    def read_line(self) -> str:
        return self._responses.pop(0)


def test_query_returns_raw_response() -> None:
    transport = FakeTransport(["Keysight,E3634A,12345,1.0"])
    scpi = ScpiProtocol(transport)
    assert scpi.identify() == "Keysight,E3634A,12345,1.0"
    assert transport.written == ["*IDN?"]


def test_query_float_parses_numeric_response() -> None:
    transport = FakeTransport(["12.0034"])
    scpi = ScpiProtocol(transport)
    assert scpi.query_float("MEASure:VOLTage:DC?") == pytest.approx(12.0034)


def test_query_float_raises_scpi_error_on_garbage() -> None:
    transport = FakeTransport(["not-a-number"])
    scpi = ScpiProtocol(transport)
    with pytest.raises(ScpiError):
        scpi.query_float("MEASure:VOLTage:DC?")


def test_check_error_no_error() -> None:
    transport = FakeTransport(['+0,"No error"'])
    scpi = ScpiProtocol(transport)
    code, message = scpi.check_error()
    assert code == 0
    assert message == "No error"


def test_check_error_maps_known_framing_error() -> None:
    transport = FakeTransport(['-511,"Framing error"'])
    scpi = ScpiProtocol(transport)
    with pytest.raises(ScpiFramingError):
        scpi.check_error()


def test_check_error_maps_unknown_code_to_generic_fault() -> None:
    transport = FakeTransport(['-222,"Data out of range"'])
    scpi = ScpiProtocol(transport)
    with pytest.raises(ScpiInstrumentFaultError) as exc_info:
        scpi.check_error()
    assert exc_info.value.code == -222


def test_check_error_raises_on_unparseable_response() -> None:
    transport = FakeTransport(["garbage response"])
    scpi = ScpiProtocol(transport)
    with pytest.raises(ScpiError):
        scpi.check_error()
