"""Driver específico da fonte programável Keysight/Agilent série E363x.

Usa exatamente os mnemônicos SCPI confirmados no User's Guide oficial
(seção 9.3 do prompt de especificação) — nenhuma variante inventada. Toda a
lógica de reconexão/heartbeat vem de `BaseSerialInstrument`; aqui só mora o
que é específico desta fonte.
"""
from __future__ import annotations

import logging

from drivers.base_instrument import BaseSerialInstrument
from drivers.exceptions import InstrumentCommunicationError

_logger = logging.getLogger("app")


class PowerSupplyE363x(BaseSerialInstrument):
    """Driver para E3631A/E3632A/E3633A/E3634A (subset de comandos comum)."""

    def on_connected(self) -> None:
        """Valida a comunicação ANTES de entrar em modo remoto.

        Ordem importa para não provocar o "apito constante": primeiro fazemos
        uma sonda diagnóstica (`*CLS` + `*IDN?`) — se o framing/cabo estiver
        errado, ela falha cedo com mensagem acionável e sem despejar uma
        sequência de comandos que bipam um a um. Só com a identidade
        confirmada é que `SYSTem:REMote` é enviado (obrigatório antes dos
        demais comandos — seção 9.2) e a fila de erros é limpa.

        Efeito colateral: também força OUTPUT OFF e limpa qualquer latch de
        OVP/OCP residual (ver `_reset_residual_state`) — chamar `connect()`/
        `reconnect()` NÃO é neutro em relação ao estado de saída/proteção da
        fonte.
        """
        identity = self._transport.probe_identity()
        _logger.info("Fonte identificada: %s", identity)
        self.scpi.write("SYSTem:REMote")
        self.scpi.clear_status()
        self.scpi.check_error()
        self._reset_residual_state()

    def _reset_residual_state(self) -> None:
        """Garante estado limpo a cada nova conexão (início de cada ensaio).

        Sem isto, se o ensaio anterior terminou com um latch de OVP/OCP
        disparado, a fonte mantém a saída travada em hardware mesmo depois
        que o novo ensaio manda `OUTPut:STATe ON` — o operador vê leituras
        de tensão/corrente bem abaixo do setpoint recém-aplicado (ex.: ~0 V
        com 12 V configurado). Cada etapa é best-effort e não interrompe a
        conexão: um erro aqui não pode impedir o ensaio de começar.
        """
        try:
            self.output_off()
        except InstrumentCommunicationError as exc:
            _logger.warning("Falha ao garantir saída desligada na conexão: %s", exc)
        for is_tripped, clear, name in (
            (self.is_overvoltage_protection_tripped, self.clear_overvoltage_protection, "OVP"),
            (self.is_overcurrent_protection_tripped, self.clear_overcurrent_protection, "OCP"),
        ):
            try:
                if is_tripped():
                    _logger.info("Latch de %s de uma sessão anterior detectado — limpando.", name)
                    clear()
            except InstrumentCommunicationError as exc:
                _logger.warning("Falha ao verificar/limpar latch de %s na conexão: %s", name, exc)

    def on_disconnecting(self) -> None:
        """Failsafe: tenta desligar a saída antes de fechar a porta.

        Best-effort — se a comunicação já estiver morta, não bloqueia o
        encerramento (quem chama precisa fechar a porta de qualquer forma).
        """
        try:
            self.output_off()
        except InstrumentCommunicationError as exc:
            _logger.warning("Falha ao desligar saída no failsafe de desconexão: %s", exc)

    def output_on(self) -> None:
        self.scpi.write("OUTPut:STATe ON")
        self.scpi.check_error()

    def output_off(self) -> None:
        self.scpi.write("OUTPut:STATe OFF")
        self.scpi.check_error()

    def is_output_on(self) -> bool:
        response = self.scpi.query("OUTPut:STATe?")
        return response.strip() in ("1", "ON")

    def set_voltage(self, volts: float) -> None:
        self.scpi.write(f"VOLTage:LEVel:IMMediate:AMPLitude {volts:.4f}")
        self.scpi.check_error()

    def get_voltage_setpoint(self) -> float:
        return self.scpi.query_float("VOLTage:LEVel:IMMediate:AMPLitude?")

    def set_current(self, amps: float) -> None:
        self.scpi.write(f"CURRent:LEVel:IMMediate:AMPLitude {amps:.4f}")
        self.scpi.check_error()

    def get_current_setpoint(self) -> float:
        return self.scpi.query_float("CURRent:LEVel:IMMediate:AMPLitude?")

    def set_voltage_range(self, range_name: str) -> None:
        """range_name em {P8V, P20V, P25V, P50V, LOW, HIGH}, conforme modelo."""
        self.scpi.write(f"VOLTage:RANGe {range_name}")
        self.scpi.check_error()

    def measure_voltage(self) -> float:
        return self.scpi.query_float("MEASure:VOLTage:DC?")

    def measure_current(self) -> float:
        return self.scpi.query_float("MEASure:CURRent:DC?")

    def apply(self, volts: float, amps: float) -> None:
        """APPLy — define tensão e corrente em um único comando."""
        self.scpi.write(f"APPLy {volts:.4f},{amps:.4f}")
        self.scpi.check_error()

    def clear_status(self) -> None:
        """*CLS — limpa fila de erros e registradores de status."""
        self.scpi.clear_status()

    def set_overvoltage_protection(
        self, level: float, enabled: bool = True, clear_latch: bool = False
    ) -> None:
        # Desativa antes de alterar o nível: sem isso o instrumento pode rejeitar
        # um novo nível enquanto OVP está ON com a saída ativa.
        # clear_latch=True somente quando OVP sabidamente disparou (restart após
        # trip): VOLT:PROT:CLEar é inválido em muitas firmwares se o latch não
        # estava ativo.
        # Cada write() é seguido de wait_complete() (*OPC?): sem isso, os 3-4
        # comandos desta sequência somam ~100+ caracteres e estouram o buffer
        # de entrada da E363x (erro 521 — ver ScpiInputBufferOverflowError),
        # já que o cabo de 3 fios não tem handshake de hardware para conter o PC.
        self.scpi.write("VOLTage:PROTection:STATe OFF")
        self.scpi.wait_complete()
        if clear_latch:
            self.scpi.write("VOLTage:PROTection:CLEar")
            self.scpi.wait_complete()
        self.scpi.write(f"VOLTage:PROTection:LEVel {level:.4f}")
        self.scpi.wait_complete()
        self.scpi.write(f"VOLTage:PROTection:STATe {'ON' if enabled else 'OFF'}")
        self.scpi.check_error()

    def clear_overvoltage_protection(self) -> None:
        # Reativa a proteção (mesmo nível de antes) após limpar o latch: só
        # dispara porque estava ARMADA, então restaurar o STATe é o que
        # realmente preserva "o próprio default da fonte" — deixar OFF
        # desarmaria uma proteção que o operador nunca pediu para desligar.
        self.scpi.write("VOLTage:PROTection:STATe OFF")
        self.scpi.wait_complete()
        self.scpi.write("VOLTage:PROTection:CLEar")
        self.scpi.wait_complete()
        self.scpi.write("VOLTage:PROTection:STATe ON")
        self.scpi.check_error()

    def is_overvoltage_protection_tripped(self) -> bool:
        response = self.scpi.query("VOLTage:PROTection:TRIPped?")
        return response.strip() in ("1", "YES")

    def set_overcurrent_protection(
        self, level: float, enabled: bool = True, clear_latch: bool = False
    ) -> None:
        # Pacing via wait_complete() pelo mesmo motivo de set_overvoltage_protection.
        self.scpi.write("CURRent:PROTection:STATe OFF")
        self.scpi.wait_complete()
        if clear_latch:
            self.scpi.write("CURRent:PROTection:CLEar")
            self.scpi.wait_complete()
        self.scpi.write(f"CURRent:PROTection:LEVel {level:.4f}")
        self.scpi.wait_complete()
        self.scpi.write(f"CURRent:PROTection:STATe {'ON' if enabled else 'OFF'}")
        self.scpi.check_error()

    def clear_overcurrent_protection(self) -> None:
        # Mesmo raciocínio de clear_overvoltage_protection(): restaura o
        # STATe após limpar o latch em vez de deixar a proteção desarmada.
        self.scpi.write("CURRent:PROTection:STATe OFF")
        self.scpi.wait_complete()
        self.scpi.write("CURRent:PROTection:CLEar")
        self.scpi.wait_complete()
        self.scpi.write("CURRent:PROTection:STATe ON")
        self.scpi.check_error()

    def is_overcurrent_protection_tripped(self) -> bool:
        response = self.scpi.query("CURRent:PROTection:TRIPped?")
        return response.strip() in ("1", "YES")
