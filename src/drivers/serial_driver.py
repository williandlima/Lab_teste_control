"""Camada de transporte serial pura (sem conhecimento de SCPI).

Responsabilidades: abrir/fechar porta, parametrização conforme manual do
instrumento, detecção automática de porta (fixa ou por VID/PID), timeout,
reconexão com backoff, e log estruturado de TX/RX em nível DEBUG.

Esta classe NUNCA deve ser instanciada/chamada na thread da GUI: ela é
pensada para rodar dentro de um QThread/worker (ver gui/main_window.py),
porque toda leitura é bloqueante até o timeout configurado.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from config import SerialConfig
from drivers.exceptions import SerialConnectionError, SerialTimeoutError

_serial_io_logger = logging.getLogger("serial_io")


@dataclass
class PortDescriptor:
    device: str
    vid: int | None
    pid: int | None
    description: str


def list_available_ports() -> list[PortDescriptor]:
    """Lista portas COM disponíveis, para fallback manual na GUI."""
    return [
        PortDescriptor(device=p.device, vid=p.vid, pid=p.pid, description=p.description)
        for p in list_ports.comports()
    ]


def find_port_by_vid_pid(vid: int, pid: int) -> str | None:
    """Localiza a porta de um adaptador USB-serial pelo VID/PID.

    Usado para sobreviver a reenumeração de porta COM (gerenciamento de
    energia do Windows pode trocar o número da porta entre sessões longas).
    """
    for port in list_ports.comports():
        if port.vid == vid and port.pid == pid:
            return port.device
    return None


class SerialTransport:
    """Transporte serial síncrono, linha-a-linha, para instrumentos SCPI."""

    def __init__(self, config: SerialConfig) -> None:
        self._config = config
        self._serial: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def resolve_port(self) -> str:
        """Resolve a porta a usar: fixa por config, ou por VID/PID."""
        if self._config.port:
            return self._config.port
        if self._config.vid is not None and self._config.pid is not None:
            found = find_port_by_vid_pid(self._config.vid, self._config.pid)
            if found:
                return found
        raise SerialConnectionError(
            "Nenhuma porta configurada e nenhum dispositivo VID/PID "
            f"({self._config.vid:#x}:{self._config.pid:#x}) encontrado."
            if self._config.vid is not None and self._config.pid is not None
            else "Nenhuma porta serial configurada (port=null e vid/pid ausentes)."
        )

    def connect(self) -> None:
        """Abre a porta serial com os parâmetros do manual do instrumento.

        Importante: a E363x é um DTE e usa handshake DTR/DSR por padrão. Com
        cabo de 3 fios (sem DTR/DSR cabeados), é necessário desabilitar o
        handshake de hardware do lado do PC (`dsrdtr=False`) e ainda assim
        forçar a linha DTR em nível alto (`force_dtr_high`), pois é essa
        linha que, fisicamente amarrada, sinaliza ao instrumento que o lado
        remoto está "presente" — sem isso a fonte trava esperando handshake.
        """
        port = self.resolve_port()
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self._config.baudrate,
                bytesize=self._config.bytesize,
                parity=self._config.parity,
                stopbits=self._config.stopbits,
                timeout=self._config.timeout_s,
                write_timeout=self._config.write_timeout_s,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False,
            )
            if self._config.force_dtr_high:
                self._serial.dtr = True
        except serial.SerialException as exc:
            raise SerialConnectionError(f"Falha ao abrir porta {port}: {exc}") from exc

        _serial_io_logger.debug("Porta %s aberta (%s)", port, self._config)

    def disconnect(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
            _serial_io_logger.debug("Porta serial fechada.")
        self._serial = None

    def write_line(self, command: str) -> None:
        """Envia um comando terminado em '\\n', conforme exigido pela E363x."""
        if self._serial is None or not self._serial.is_open:
            raise SerialConnectionError("Tentativa de escrita em porta não conectada.")
        payload = (command.strip() + "\n").encode("ascii")
        try:
            self._serial.write(payload)
        except serial.SerialTimeoutException as exc:
            raise SerialTimeoutError(f"Timeout ao escrever '{command}': {exc}") from exc
        _serial_io_logger.debug("TX: %s", command.strip())

    def read_line(self) -> str:
        """Lê uma linha de resposta, terminada em '\\n', até o timeout."""
        if self._serial is None or not self._serial.is_open:
            raise SerialConnectionError("Tentativa de leitura em porta não conectada.")
        raw = self._serial.readline()
        if not raw:
            raise SerialTimeoutError("Nenhuma resposta recebida dentro do timeout.")
        response = raw.decode("ascii", errors="replace").strip()
        _serial_io_logger.debug("RX: %s", response)
        return response

    def reconnect_with_backoff(self, max_retries: int, backoff_base_s: float, multiplier: float) -> bool:
        """Tenta reabrir a porta com backoff exponencial.

        Retorna True se reconectou, False se esgotou as tentativas. Não
        levanta exceção para que a state machine decida a transição (ex.
        CommError) em vez de propagar um traceback bruto.
        """
        self.disconnect()
        delay = backoff_base_s
        for attempt in range(1, max_retries + 1):
            try:
                self.connect()
                _serial_io_logger.info("Reconectado na tentativa %d.", attempt)
                return True
            except SerialConnectionError as exc:
                _serial_io_logger.warning(
                    "Tentativa de reconexão %d/%d falhou: %s", attempt, max_retries, exc
                )
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= multiplier
        return False
