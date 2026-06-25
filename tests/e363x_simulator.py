"""Simulador de fonte Keysight/Agilent E3631A no nível do *transporte serial*.

Existe para podermos "simular antes de codar" (pedido da revisão sênior): em
vez de validar a correção de RS-232 contra hardware real, modelamos aqui os
comportamentos do manual oficial que produzem os dois sintomas relatados em
campo — **timeout** e **apito constante** — e exercitamos o driver contra eles.

Fatos do manual modelados (E3631A User's Guide, seção RS-232):
- Handshake DTR/DSR: a fonte (DTE) só transmite respostas enquanto vê a
  linha DSR em nível verdadeiro. Num cabo de 3 fios sem jumper DTR-DSR, o DSR
  da fonte fica flutuando/falso e ela **segura as respostas** -> o PC nunca
  lê nada -> `readline()` devolve b"" -> timeout. (sintoma 1)
- Beeper de erro: cada erro enfileirado (framing/comando) emite um bip. Se os
  parâmetros seriais não casam (baud/paridade/stop bits), todo byte recebido
  vira lixo de framing -> um erro por comando -> **apito constante**. (sintoma 2)
- Modo remoto: comandos só são aceitos após `SYSTem:REMote`; antes disso a
  fonte enfileira erro (e bipa) para comandos de configuração.

A API replicada é só o subconjunto de `serial.Serial` que `SerialTransport`
usa: `is_open`, `dtr`, `rts`, `write`, `readline`, `reset_input_buffer`,
`reset_output_buffer`, `close`.
"""
from __future__ import annotations

from collections import deque

# Parâmetros "físicos" configurados no painel frontal da fonte simulada.
_PANEL_BAUDRATE = 9600
_PANEL_PARITY = "N"
_PANEL_STOPBITS = 2

_IDN_RESPONSE = "Agilent Technologies,E3631A,0,2.1-5.0-1.0"


class SimulatedE3631A:
    """Fake de `serial.Serial` que reproduz os modos de falha do manual.

    Parâmetros de cenário (combináveis):
        dsr_wired: se False, modela cabo de 3 fios sem jumper DTR-DSR -> a
            fonte nunca enxerga DSR verdadeiro e segura todas as respostas.
        params_match: se False, baud/paridade/stop bits divergem do painel ->
            framing error + bip a cada comando, respostas viram lixo.
    """

    def __init__(
        self,
        *,
        baudrate: int = _PANEL_BAUDRATE,
        parity: str = _PANEL_PARITY,
        stopbits: int = _PANEL_STOPBITS,
        dsr_wired: bool = True,
        **_ignored: object,
    ) -> None:
        self.is_open = True
        self.dtr = False
        self.rts = False
        self._params_match = (
            baudrate == _PANEL_BAUDRATE
            and parity == _PANEL_PARITY
            and stopbits == _PANEL_STOPBITS
        )
        self._dsr_wired = dsr_wired
        self._remote = False
        self._rx_buffer = b""
        self._tx_lines: deque[bytes] = deque()
        # Observáveis para asserções nos testes:
        self.beep_count = 0
        self.error_queue: list[tuple[int, str]] = []

    # -- handshake -----------------------------------------------------------

    @property
    def _dsr_seen_true(self) -> bool:
        """A fonte vê DSR verdadeiro só se o cabo o carrega e o PC ergueu DTR."""
        return self._dsr_wired and self.dtr

    # -- API usada pelo SerialTransport -------------------------------------

    def reset_input_buffer(self) -> None:
        # Do ponto de vista do PC, "input" são os bytes que a fonte já enfileirou
        # para enviar e ainda não foram lidos.
        self._tx_lines.clear()

    def reset_output_buffer(self) -> None:
        # Buffer de saída do PC (bytes a caminho da fonte) — não modelado.
        self._rx_buffer = b""

    def write(self, payload: bytes) -> int:
        if not self._params_match:
            # Bytes chegam corrompidos: erro de framing a cada comando (bip).
            self._raise_beep(-511, "Framing error")
            # Mesmo assim devolve algo ilegível, como faria a UART real.
            self._tx_lines.append(b"\x00\xff garbage\n")
            return len(payload)

        command = payload.decode("ascii", errors="replace").strip().upper()
        self._handle_command(command)
        return len(payload)

    def readline(self) -> bytes:
        # Sintoma 1: sem DSR verdadeiro a fonte segura tudo -> PC vê timeout.
        if not self._dsr_seen_true:
            return b""
        if self._tx_lines:
            return self._tx_lines.popleft()
        return b""

    def close(self) -> None:
        self.is_open = False

    # -- lógica de instrumento ----------------------------------------------

    def _raise_beep(self, code: int, message: str) -> None:
        self.beep_count += 1
        self.error_queue.append((code, message))

    def _handle_command(self, command: str) -> None:
        if command == "*CLS":
            self.error_queue.clear()
            return
        if command == "*IDN?":
            self._tx_lines.append((_IDN_RESPONSE + "\n").encode("ascii"))
            return
        if command in ("SYSTEM:REMOTE", "SYST:REM"):
            self._remote = True
            return
        if command == "SYSTEM:ERROR?" or command == "SYST:ERR?":
            if self.error_queue:
                code, msg = self.error_queue.pop(0)
            else:
                code, msg = 0, "No error"
            self._tx_lines.append(f'{code:+d},"{msg}"\n'.encode("ascii"))
            return
        # Demais comandos exigem modo remoto; fora dele a fonte bipa e ignora.
        if not self._remote:
            self._raise_beep(-203, "Command protected (local mode)")
            return
        if command.endswith("?"):
            # Resposta numérica plausível para queries de medição/setpoint.
            self._tx_lines.append(b"0.000\n")
