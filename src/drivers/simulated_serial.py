"""Fonte E363x *simulada* no nível do transporte serial (modo demonstração).

Diferente de `tests/e363x_simulator.py` — que modela os *modos de falha* de
RS-232 (timeout/apito) para exercitar o driver — este simulador modela uma
fonte **saudável e funcional**: responde a `*IDN?`, entra em modo remoto,
aceita `APPLy`/`OUTPut` e devolve medições de tensão/corrente próximas ao
setpoint. Serve para o operador rodar o fluxo completo do app (cadastro ->
parâmetros -> monitoramento -> avaliação -> relatório) **sem a fonte física
conectada**, gerando uma curva realista no gráfico ao vivo.

Ativado por `serial.simulate: true` em `config/app_config.yaml`. A API
replicada é só o subconjunto de `serial.Serial` que `SerialTransport` usa:
`is_open`, `dtr`, `rts`, `write`, `readline`, `reset_input_buffer`,
`reset_output_buffer`, `close`.
"""
from __future__ import annotations

import random
from collections import deque

_IDN_RESPONSE = "Avibras Aeroco,E363x-SIMULADO,0,1.0"


class SimulatedE363xSerial:
    """Fake de `serial.Serial` que reproduz uma fonte saudável (modo demo)."""

    def __init__(self, *, seed: int | None = None, **_ignored: object) -> None:
        self.is_open = True
        self.dtr = False
        self.rts = False
        self._remote = False
        self._output_on = False
        self._set_voltage = 0.0
        self._set_current = 0.0
        self._tx_lines: deque[bytes] = deque()
        self._rng = random.Random(seed)

    # -- API usada pelo SerialTransport -------------------------------------

    def reset_input_buffer(self) -> None:
        self._tx_lines.clear()

    def reset_output_buffer(self) -> None:
        pass

    def write(self, payload: bytes) -> int:
        command = payload.decode("ascii", errors="replace").strip()
        self._handle_command(command)
        return len(payload)

    def readline(self) -> bytes:
        if self._tx_lines:
            return self._tx_lines.popleft()
        return b""

    def close(self) -> None:
        self.is_open = False

    # -- lógica de instrumento ----------------------------------------------

    def _reply(self, text: str) -> None:
        self._tx_lines.append((text + "\n").encode("ascii"))

    def _measured_voltage(self) -> float:
        """Tensão medida ~ setpoint com pequeno ruído (estabiliza < tolerância)."""
        if not self._output_on:
            return self._rng.uniform(0.0, 0.002)
        return self._set_voltage + self._rng.uniform(-0.01, 0.01)

    def _measured_current(self) -> float:
        """Corrente medida: carga consome ~metade do limite, com ruído leve."""
        if not self._output_on:
            return self._rng.uniform(0.0, 0.001)
        return max(0.0, self._set_current * 0.5 + self._rng.uniform(-0.005, 0.005))

    def _handle_command(self, command: str) -> None:
        upper = command.upper()

        if upper == "*CLS":
            return
        if upper == "*IDN?":
            self._reply(_IDN_RESPONSE)
            return
        if upper in ("SYSTEM:REMOTE", "SYST:REM"):
            self._remote = True
            return
        if upper in ("SYSTEM:LOCAL", "SYST:LOC"):
            self._remote = False
            return
        if upper in ("SYSTEM:ERROR?", "SYST:ERR?"):
            self._reply('+0,"No error"')
            return
        if upper in ("*RST", "*TST?"):
            if upper == "*TST?":
                self._reply("0")
            return

        if upper.startswith("APPLY") or upper.startswith("APPL"):
            self._apply(command)
            return
        if upper.startswith("VOLTAGE:LEVEL") or upper.startswith("VOLT:LEV"):
            self._set_or_query(command, "voltage")
            return
        if upper.startswith("CURRENT:LEVEL") or upper.startswith("CURR:LEV"):
            self._set_or_query(command, "current")
            return
        if upper.startswith("OUTPUT:STATE") or upper.startswith("OUTP:STAT"):
            if upper.endswith("?"):
                self._reply("1" if self._output_on else "0")
            else:
                self._output_on = upper.split()[-1] in ("ON", "1")
            return
        if upper.startswith("MEASURE:VOLTAGE") or upper.startswith("MEAS:VOLT"):
            self._reply(f"{self._measured_voltage():.4f}")
            return
        if upper.startswith("MEASURE:CURRENT") or upper.startswith("MEAS:CURR"):
            self._reply(f"{self._measured_current():.4f}")
            return

        # Proteções (OVP/OCP), range, etc.: aceitos silenciosamente; uma query
        # desconhecida ainda recebe um numérico plausível para não travar.
        if upper.endswith("?"):
            self._reply("0.000")

    def _apply(self, command: str) -> None:
        try:
            args = command.split(None, 1)[1]
            volts_str, amps_str = args.split(",")
            self._set_voltage = float(volts_str)
            self._set_current = float(amps_str)
        except (IndexError, ValueError):
            pass

    def _set_or_query(self, command: str, kind: str) -> None:
        if command.strip().endswith("?"):
            value = self._set_voltage if kind == "voltage" else self._set_current
            self._reply(f"{value:.4f}")
            return
        try:
            value = float(command.split()[-1])
        except ValueError:
            return
        if kind == "voltage":
            self._set_voltage = value
        else:
            self._set_current = value
