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
from drivers.exceptions import (
    ScpiFramingError,
    SerialConnectionError,
    SerialTimeoutError,
)

_serial_io_logger = logging.getLogger("serial_io")

# Um *IDN? válido da E363x é "fabricante,modelo,serie,firmware": sempre tem
# vírgulas. Resposta sem vírgula (ou vazia) denuncia framing/baud errados, não
# o conteúdo real do instrumento.
_IDN_MIN_COMMAS = 1


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
        # Porta escolhida pelo operador na GUI (tem prioridade sobre a config).
        self._port_override: str | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def set_port_override(self, port: str | None) -> None:
        """Define a porta COM escolhida manualmente pelo operador na GUI.

        Tem prioridade sobre `port`/VID-PID da config. Passar None volta a
        usar a resolução automática.
        """
        self._port_override = port or None

    def resolve_port(self) -> str:
        """Resolve a porta a usar: escolha do operador, fixa por config, ou VID/PID."""
        if self._port_override:
            return self._port_override
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
        if self._config.simulate:
            self._connect_simulated()
            return
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
                dsrdtr=self._config.dsrdtr,
                rtscts=self._config.rtscts,
                xonxoff=False,
            )
            # Ergue DTR/RTS pelo lado do PC: em cabos que cruzam essas linhas é
            # o que faz a fonte enxergar DSR verdadeiro e parar de segurar as
            # respostas (causa nº1 de timeout num cabo de 3 fios).
            if self._config.force_dtr_high:
                self._serial.dtr = True
            if self._config.force_rts_high:
                self._serial.rts = True
            # Descarta qualquer lixo deixado no buffer por uma sessão anterior
            # (evita que uma resposta órfã seja lida como se fosse da atual).
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except serial.SerialException as exc:
            raise SerialConnectionError(f"Falha ao abrir porta {port}: {exc}") from exc

        _serial_io_logger.debug("Porta %s aberta (%s)", port, self._config)

    def _connect_simulated(self) -> None:
        """Abre uma fonte simulada (modo demonstração) em vez de uma porta real."""
        from drivers.simulated_serial import SimulatedE363xSerial

        self._serial = SimulatedE363xSerial()
        if self._config.force_dtr_high:
            self._serial.dtr = True
        if self._config.force_rts_high:
            self._serial.rts = True
        _serial_io_logger.info("Modo SIMULAÇÃO ativo: usando fonte E363x simulada.")

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

    def probe_identity(self) -> str:
        """Sondagem mínima e diagnóstica de presença do instrumento.

        Sequência deliberadamente curta para NÃO provocar o "apito constante":
        em vez de despejar REMote/CLS/ERRor? (cada um vira um bip quando o
        framing está errado), envia só `*CLS` (limpa a fila de erros sem
        precisar de resposta) e um único `*IDN?`. A partir do que volta,
        classifica a falha de forma acionável para o operador:

        - resposta vazia (timeout)  -> cabo/baud/handshake. A E363x segura as
          respostas enquanto não vê DSR verdadeiro (cabo de 3 fios sem jumper
          DTR-DSR é a causa clássica).
        - resposta sem vírgula (lixo) -> framing: paridade/data bits/stop bits
          ou baudrate divergentes do painel frontal da fonte.
        - resposta válida -> devolve a string de identificação.
        """
        if self._serial is None or not self._serial.is_open:
            raise SerialConnectionError("Sonda chamada com a porta fechada.")
        self._serial.reset_input_buffer()
        self.write_line("*CLS")
        try:
            response = self.query_identity()
        except SerialTimeoutError as exc:
            raise SerialTimeoutError(
                "Sem resposta da fonte (timeout). Verifique: porta COM correta, "
                "cabo/adaptador, baudrate igual ao painel frontal e o handshake "
                "DTR/DSR (em cabo de 3 fios, faça o jumper DTR-DSR no conector "
                "da fonte)."
            ) from exc
        if response.count(",") < _IDN_MIN_COMMAS:
            raise ScpiFramingError(
                f"Resposta ilegível ao *IDN? ('{response}'). Indício de erro de "
                "framing: confira paridade/data bits/stop bits e o baudrate "
                "configurados no painel frontal da E363x."
            )
        return response

    def query_identity(self) -> str:
        """Envia `*IDN?` e lê uma linha (sem classificação de erro). Uso interno."""
        self.write_line("*IDN?")
        return self.read_line()

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
