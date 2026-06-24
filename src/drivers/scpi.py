"""Protocolo SCPI genérico, independente do instrumento.

Conhece apenas a sintaxe SCPI (terminação de comando, formato de resposta de
erro `SYSTem:ERRor?`, comandos comuns *IDN?/*RST/*CLS/*TST?) — nenhum
mnemônico específico da E363x mora aqui. Isso permite reaproveitar esta
classe para outros instrumentos SCPI no futuro (osciloscópio, multímetro).
"""
from __future__ import annotations

import logging
import re

from drivers.exceptions import ScpiError, build_scpi_error
from drivers.serial_driver import SerialTransport

_logger = logging.getLogger("serial_io")

# Formato típico de resposta da SYSTem:ERRor?: +0,"No error" ou -511,"Framing error"
_ERROR_RESPONSE_RE = re.compile(r'^([+-]?\d+)\s*,\s*"(.*)"$')


class ScpiProtocol:
    """Camada de framing/parsing SCPI sobre um `SerialTransport`."""

    def __init__(self, transport: SerialTransport) -> None:
        self._transport = transport

    def write(self, command: str) -> None:
        self._transport.write_line(command)

    def query(self, command: str) -> str:
        self._transport.write_line(command)
        return self._transport.read_line()

    def query_float(self, command: str) -> float:
        response = self.query(command)
        try:
            return float(response)
        except ValueError as exc:
            raise ScpiError(f"Resposta não numérica para '{command}': '{response}'") from exc

    def identify(self) -> str:
        """*IDN? — fabricante, modelo, número de série, versão de firmware."""
        return self.query("*IDN?")

    def reset(self) -> None:
        """*RST — restaura o instrumento aos valores de fábrica."""
        self.write("*RST")

    def clear_status(self) -> None:
        """*CLS — limpa registradores de status e a fila de erros."""
        self.write("*CLS")

    def self_test(self) -> bool:
        """*TST? — executa autoteste interno; True se passou (0)."""
        result = self.query("*TST?")
        return result.strip() == "0"

    def check_error(self) -> tuple[int, str]:
        """Consulta `SYSTem:ERRor?` e levanta exceção tipada se houver erro.

        Retorna (0, "No error") em caso de fila de erros vazia.
        """
        response = self.query("SYSTem:ERRor?")
        match = _ERROR_RESPONSE_RE.match(response)
        if not match:
            raise ScpiError(f"Resposta inesperada de SYSTem:ERRor?: '{response}'")
        code, message = int(match.group(1)), match.group(2)
        if code != 0:
            raise build_scpi_error(code, message)
        return code, message
