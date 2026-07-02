"""Hierarquia de exceções tipadas para a camada de drivers.

Evita `except Exception` genérico nas camadas superiores (NFR seção 5): cada
falha de comunicação/protocolo tem um tipo específico, permitindo que o
core/state_machine decida a política de retry/abort por tipo de erro em vez
de por inspeção de mensagem de texto.
"""
from __future__ import annotations


class InstrumentCommunicationError(Exception):
    """Erro base de comunicação com um instrumento serial."""


class SerialConnectionError(InstrumentCommunicationError):
    """Falha ao abrir, reabrir ou manter a porta serial."""


class SerialTimeoutError(InstrumentCommunicationError):
    """Nenhuma resposta recebida dentro do timeout configurado."""


class ScpiError(InstrumentCommunicationError):
    """Erro genérico de protocolo SCPI (resposta malformada/inesperada)."""


class ScpiFramingError(ScpiError):
    """Equivalente ao erro de instrumento -511 (framing error).

    Causa típica: stop bits configurados errado (E363x exige 2, não 1).
    """


class ScpiOverrunError(ScpiError):
    """Equivalente ao erro de instrumento -512 (overrun error)."""


class ScpiParityError(ScpiError):
    """Equivalente ao erro de instrumento -513 (parity error)."""


class ScpiInputBufferOverflowError(ScpiError):
    """Equivalente ao erro de instrumento -521 (input buffer overflow).

    Causa típica: múltiplos comandos enfileirados sem aguardar resposta
    (buffer de entrada da E3634A é de ~100 caracteres, sem handshake DTR/DSR
    no cabo de 3 fios).
    """


class InstrumentRangeOutOfBoundsError(InstrumentCommunicationError):
    """O setpoint pedido não cabe em nenhuma faixa V/A configurada do instrumento.

    Detectado no cliente, antes de qualquer I/O com a fonte — dá uma mensagem
    acionável (qual faixa falta configurar) em vez do "-222: Data out of
    range" genérico que o instrumento devolveria.
    """


class ScpiInstrumentFaultError(ScpiError):
    """SYSTem:ERRor? retornou um código de erro não mapeado explicitamente."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"SCPI error {code}: {message}")


_ERROR_CODE_MAP: dict[int, type[ScpiError]] = {
    -511: ScpiFramingError,
    -512: ScpiOverrunError,
    -513: ScpiParityError,
    -521: ScpiInputBufferOverflowError,
}


def build_scpi_error(code: int, message: str) -> ScpiError:
    """Mapeia um código `SYSTem:ERRor?` para o tipo de exceção específico."""
    error_cls = _ERROR_CODE_MAP.get(code)
    if error_cls is not None:
        return error_cls(f"SCPI error {code}: {message}")
    return ScpiInstrumentFaultError(code, message)
