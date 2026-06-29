"""Classe base abstrata para instrumentos SCPI sobre serial.

Centraliza o que é comum a QUALQUER instrumento (E363x hoje; osciloscópio
ou multímetro no futuro): ciclo de vida da conexão, reconexão com backoff e
heartbeat. Drivers específicos (ex. `hardware/power_supply.py`) herdam desta
classe e só implementam os mnemônicos SCPI próprios do instrumento — assim a
lógica de reconexão/log nunca é duplicada entre drivers.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from config import ReconnectionConfig, SerialConfig
from drivers.exceptions import InstrumentCommunicationError
from drivers.scpi import ScpiProtocol
from drivers.serial_driver import SerialTransport

_logger = logging.getLogger("app")


class BaseSerialInstrument(ABC):
    """Ciclo de vida comum: conectar, desconectar, reconectar, heartbeat."""

    def __init__(self, serial_config: SerialConfig, reconnection_config: ReconnectionConfig) -> None:
        self._transport = SerialTransport(serial_config)
        self._scpi = ScpiProtocol(self._transport)
        self._reconnection_config = reconnection_config
        self._last_heartbeat_monotonic: float | None = None

    @property
    def scpi(self) -> ScpiProtocol:
        return self._scpi

    @property
    def is_connected(self) -> bool:
        return self._transport.is_open

    @property
    def last_identity(self) -> str | None:
        """Última string *IDN? lida da fonte (rastreabilidade do ensaio)."""
        return self._transport.last_identity

    def set_port(self, port: str | None) -> None:
        """Define a porta COM escolhida pelo operador (prioridade sobre a config)."""
        self._transport.set_port_override(port)

    def set_simulate(self, enabled: bool | None) -> None:
        """Liga/desliga o modo simulação (fonte virtual) em tempo de execução."""
        self._transport.set_simulate(enabled)

    def reset_io_buffers(self) -> None:
        """Limpa buffers serial para ressincronizar após um timeout de leitura."""
        self._transport.reset_io_buffers()

    def test_connection(self) -> str:
        """Abre a porta, sonda *IDN? e fecha — diagnóstico sem efeitos colaterais.

        Não entra em modo remoto nem mexe na saída: serve para o operador
        validar cabo/porta/parâmetros antes de iniciar um teste real. Devolve a
        string de identificação ou propaga uma exceção tipada com a causa
        provável (timeout vs framing). Garante o fechamento da porta mesmo em
        falha, para não deixar o recurso preso.
        """
        already_open = self._transport.is_open
        if not already_open:
            self._transport.connect()
        try:
            return self._transport.probe_identity()
        finally:
            if not already_open:
                self._transport.disconnect()

    def connect(self) -> None:
        """Abre a porta e executa a inicialização específica do instrumento."""
        self._transport.connect()
        self.on_connected()
        _logger.info("%s conectado.", self.__class__.__name__)

    def disconnect(self) -> None:
        """Executa desligamento seguro específico antes de fechar a porta."""
        try:
            self.on_disconnecting()
        finally:
            self._transport.disconnect()
            _logger.info("%s desconectado.", self.__class__.__name__)

    def reconnect(self) -> bool:
        """Reabre a porta com backoff e reaplica a inicialização do instrumento."""
        reconnected = self._transport.reconnect_with_backoff(
            max_retries=self._reconnection_config.max_retries,
            backoff_base_s=self._reconnection_config.backoff_base_s,
            multiplier=self._reconnection_config.backoff_multiplier,
        )
        if reconnected:
            self.on_connected()
        return reconnected

    def heartbeat(self) -> bool:
        """Sondagem leve de vivacidade (`*IDN?`), independente do ciclo de medição.

        Pensado para rodar num timer próprio (ex. a cada
        `reconnection.heartbeat_interval_s`), não dentro do laço de
        monitoramento de tensão/corrente — mistura os dois aumentaria a
        chance de colisão de comandos no buffer de entrada da fonte.
        """
        try:
            self.identify()
            self._last_heartbeat_monotonic = time.monotonic()
            return True
        except InstrumentCommunicationError as exc:
            _logger.warning("Heartbeat falhou em %s: %s", self.__class__.__name__, exc)
            return False

    def identify(self) -> str:
        return self._scpi.identify()

    @abstractmethod
    def on_connected(self) -> None:
        """Hook chamado após a porta abrir: inicialização específica (ex. SYSTem:REMote)."""

    def on_disconnecting(self) -> None:
        """Hook chamado antes de fechar a porta. Default: nenhuma ação.

        Drivers que controlam saída de energia (ex. fonte) devem sobrescrever
        para garantir desligamento seguro (failsafe) mesmo em desconexão.
        """
