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
        """Coloca o instrumento em modo remoto e limpa a fila de erros.

        `SYSTem:REMote` é obrigatório antes de qualquer outro comando
        (seção 9.2) — sem ele, comandos subsequentes são ignorados pelo
        painel frontal da fonte.
        """
        self.scpi.write("SYSTem:REMote")
        self.scpi.clear_status()
        self.scpi.check_error()

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

    def set_overvoltage_protection(self, level: float, enabled: bool = True) -> None:
        self.scpi.write(f"VOLTage:PROTection:LEVel {level:.4f}")
        self.scpi.write(f"VOLTage:PROTection:STATe {'ON' if enabled else 'OFF'}")
        self.scpi.check_error()

    def clear_overvoltage_protection(self) -> None:
        self.scpi.write("VOLTage:PROTection:CLEar")
        self.scpi.check_error()

    def set_overcurrent_protection(self, level: float, enabled: bool = True) -> None:
        self.scpi.write(f"CURRent:PROTection:LEVel {level:.4f}")
        self.scpi.write(f"CURRent:PROTection:STATe {'ON' if enabled else 'OFF'}")
        self.scpi.check_error()

    def clear_overcurrent_protection(self) -> None:
        self.scpi.write("CURRent:PROTection:CLEar")
        self.scpi.check_error()
