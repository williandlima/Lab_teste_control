"""Driver específico da fonte programável Keysight/Agilent série E363x.

Usa exatamente os mnemônicos SCPI confirmados no User's Guide oficial
(seção 9.3 do prompt de especificação) — nenhuma variante inventada. Toda a
lógica de reconexão/heartbeat vem de `BaseSerialInstrument`; aqui só mora o
que é específico desta fonte.
"""
from __future__ import annotations

import logging

from config import ReconnectionConfig, SerialConfig, VoltageRange
from drivers.base_instrument import BaseSerialInstrument
from drivers.exceptions import InstrumentCommunicationError, InstrumentRangeOutOfBoundsError

_logger = logging.getLogger("app")


class PowerSupplyE363x(BaseSerialInstrument):
    """Driver para E3631A/E3632A/E3633A/E3634A (subset de comandos comum)."""

    def __init__(
        self,
        serial_config: SerialConfig,
        reconnection_config: ReconnectionConfig,
        ranges: tuple[VoltageRange, ...] = (),
    ) -> None:
        super().__init__(serial_config, reconnection_config)
        # Ordenadas pelo teto de tensão: a faixa mais "justa" que cobre o
        # setpoint pedido é preferida (mais resolução), só cai pra próxima se
        # a atual não comportar a tensão OU a corrente pedidas.
        self._ranges = tuple(sorted(ranges, key=lambda r: r.max_voltage))
        # None = desconhecida (nunca sondada nesta conexão) — força o 1º
        # apply() da sessão a mandar VOLTage:RANGe mesmo que, por coincidência,
        # a faixa desejada seja a mesma que já estava ativa fisicamente: não dá
        # pra confiar em estado carregado de uma sessão anterior nem em ajuste
        # manual do operador pelo painel frontal entre ensaios.
        self._active_range_name: str | None = None
        # None = seleção automática (comportamento padrão de _ensure_range).
        # Definido (nome de uma faixa configurada) = o operador pediu para
        # travar nessa faixa explicitamente (ex.: manter resolução da LOW
        # mesmo que o próximo setpoint também coubesse na HIGH) — nesse caso
        # _ensure_range NUNCA escolhe outra faixa sozinho, só valida que o
        # setpoint cabe na faixa forçada e levanta erro acionável se não couber.
        self._forced_range_name: str | None = None
        # Espelha o último OUTPut:STATe que ESTE driver mandou (não sondado
        # do instrumento) — existe só para a decisão de log em _ensure_range
        # (avisar se uma troca de faixa acontece com a saída ligada) sem
        # gastar um round-trip serial extra nesse caminho, que roda a cada
        # passo de uma sequência multi-step.
        self._output_on: bool = False

    @property
    def ranges(self) -> tuple[VoltageRange, ...]:
        """Faixas V/A configuradas (ordenadas por teto de tensão), só leitura.

        Exposto para a GUI dar feedback visual de faixa (ver
        gui/widgets/range_feedback.py) sem acessar o atributo "privado".
        """
        return self._ranges

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
        # Idem: não confia na faixa V/A que ficou ativa de uma sessão
        # anterior (ou de ajuste manual no painel) — força o próximo apply()
        # a selecionar explicitamente, mesmo que calhe de ser a mesma.
        self._active_range_name = None

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
        """Failsafe: desliga a saída e devolve a fonte ao painel frontal.

        Best-effort — se a comunicação já estiver morta, não bloqueia o
        encerramento (quem chama precisa fechar a porta de qualquer forma).
        Sem o `SYSTem:LOCal`, a fonte fica presa em modo remoto entre
        ensaios (só `on_connected()` reafirma REMote na conexão seguinte,
        nunca solta LOCal); devolver o controle ao painel frontal aqui evita
        deixar a fonte "travada" para o operador caso o app não seja
        reaberto logo em seguida.
        """
        try:
            self.output_off()
        except InstrumentCommunicationError as exc:
            _logger.warning("Falha ao desligar saída no failsafe de desconexão: %s", exc)
        try:
            self.scpi.write("SYSTem:LOCal")
        except InstrumentCommunicationError as exc:
            _logger.warning("Falha ao devolver a fonte ao modo local na desconexão: %s", exc)

    def output_on(self) -> None:
        self.scpi.write("OUTPut:STATe ON")
        self.scpi.check_error()
        self._output_on = True

    def output_off(self) -> None:
        self.scpi.write("OUTPut:STATe OFF")
        self.scpi.check_error()
        self._output_on = False

    def is_output_on(self) -> bool:
        """Sonda o estado REAL da saída via SCPI (round-trip serial).

        Use isto quando precisar de certeza (ex.: diagnóstico); para uma
        decisão interna barata (ver `_ensure_range`), prefira o cache
        `self._output_on`, que este driver já mantém a partir de todo
        `output_on()`/`output_off()` que ele mesmo emite.
        """
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

    def set_forced_range(self, range_name: str | None) -> None:
        """Trava a seleção de faixa em `range_name`, ou volta ao automático (None).

        Uso: o operador escolhe explicitamente uma faixa na GUI (Saída manual
        ou Parâmetros do ensaio) em vez de deixar `_ensure_range` escolher a
        mais "justa" sozinha — por exemplo, para manter mais resolução na LOW
        mesmo num passo que também caberia na HIGH. Chamar com None restaura
        o comportamento automático (padrão). Não faz I/O por si só: o efeito
        só aparece no próximo `apply()`/`set_voltage()`.
        """
        self._forced_range_name = range_name
        # Força a próxima chamada a reafirmar a faixa explicitamente mesmo
        # que, por coincidência, seja a mesma que já estava ativa — mesma
        # cautela de on_connected() quanto a estado herdado.
        self._active_range_name = None

    @staticmethod
    def find_fitting_range(
        volts: float, amps: float, ranges: tuple[VoltageRange, ...]
    ) -> VoltageRange | None:
        """Faixa mais "justa" (menor teto de tensão) que comporta volts/amps.

        Função pura, sem I/O — reaproveitada pela GUI para dar feedback visual
        de faixa em tempo real (cor/tooltip nos campos) sem depender de uma
        conexão serial aberta. `ranges` já deve vir ordenada por max_voltage
        crescente (ver __init__); só ordena de novo aqui por segurança, já
        que quem chama pode passar `app_config.instrument.ranges` direto.
        """
        candidates = sorted(ranges, key=lambda r: r.max_voltage)
        return next(
            (r for r in candidates if volts <= r.max_voltage and amps <= r.max_current), None
        )

    @staticmethod
    def classify_range_fit(
        volts: float,
        amps: float,
        ranges: tuple[VoltageRange, ...],
        forced_range_name: str | None = None,
    ) -> tuple[VoltageRange | None, VoltageRange | None, bool]:
        """Decide qual faixa um `apply(volts, amps)` usaria, sem I/O.

        Função pura — ÚNICA fonte da regra de negócio "o que cabe em qual
        faixa", chamada tanto por `_ensure_range` (decide o que enviar/
        levantar) quanto por `gui/widgets/range_feedback.evaluate_range_fit`
        (decide cor/mensagem na tela). Sem isto, driver e GUI cada um
        reimplementava a mesma comparação separadamente — bastava uma
        diverência sutil (ex.: tratamento de nome de faixa forçada
        inexistente) para a pré-visualização da tela mostrar "OK" num
        setpoint que o instrumento real recusaria, ou vice-versa.

        Retorna (faixa_selecionada, faixa_alternativa, faixa_forcada_existe):
        - Automático (`forced_range_name=None`): selecionada = faixa mais
          justa que cabe (ou None se nenhuma cabe); alternativa sempre None.
        - Forçado e cabe: selecionada = a própria faixa forçada.
        - Forçado e NÃO cabe (ou nome forçado não existe em `ranges`):
          selecionada=None; alternativa = melhor faixa que serviria (ou None
          se nada serve); `faixa_forcada_existe` diz se o nome ao menos é
          válido, para distinguir "typo na config" de "setpoint grande demais".
        """
        if not ranges:
            return None, None, True
        if forced_range_name is not None:
            forced = next((r for r in ranges if r.name == forced_range_name), None)
            if forced is not None and volts <= forced.max_voltage and amps <= forced.max_current:
                return forced, None, True
            alternative = PowerSupplyE363x.find_fitting_range(volts, amps, ranges)
            return None, alternative, forced is not None
        return PowerSupplyE363x.find_fitting_range(volts, amps, ranges), None, True

    def _ensure_range(self, volts: float, amps: float) -> None:
        """Seleciona a faixa V/A que comporta o setpoint pedido, se preciso.

        Sem isto, um `apply()` com tensão acima do teto da faixa ATIVA falha
        com "SCPI error -222: Data out of range" mesmo que o valor caiba
        perfeitamente numa faixa maior nunca selecionada — o app nunca
        mandava `VOLTage:RANGe`, então a fonte ficava na faixa que já
        estivesse (painel frontal ou sessão anterior). Sem faixas
        configuradas (`instrument.ranges` vazio), não faz nada — mantém o
        comportamento anterior para instrumentos de faixa única/não mapeados.
        Só protege `apply()`: `set_voltage()`/`set_current()` continuam sem
        gerenciamento de faixa (nenhum caminho do app os chama diretamente
        hoje — se um novo caminho passar a usá-los, precisa chamar
        `_ensure_range` também, ou passar por `apply()`).

        Com uma faixa FORÇADA (`set_forced_range`), a seleção automática é
        desligada: só valida que o setpoint cabe na faixa pedida pelo
        operador e nunca escolhe outra sozinha, mesmo que uma faixa maior
        fosse tecnicamente compatível.
        """
        if not self._ranges:
            return
        selected, alternative, forced_exists = self.classify_range_fit(
            volts, amps, self._ranges, self._forced_range_name
        )
        if selected is None:
            if self._forced_range_name is not None and not forced_exists:
                raise InstrumentRangeOutOfBoundsError(
                    f"Faixa forçada '{self._forced_range_name}' não existe em "
                    f"'instrument.ranges' (app_config.yaml)."
                )
            if self._forced_range_name is not None:
                forced = next(r for r in self._ranges if r.name == self._forced_range_name)
                raise InstrumentRangeOutOfBoundsError(
                    f"{volts:.2f} V / {amps:.3f} A não cabe na faixa '{forced.name}' "
                    f"(até {forced.max_voltage:.2f} V / {forced.max_current:.3f} A), que foi "
                    "forçada manualmente pelo operador. Escolha outra faixa ou volte para "
                    "'Automática'."
                )
            raise InstrumentRangeOutOfBoundsError(
                f"{volts:.2f} V / {amps:.3f} A não cabe em nenhuma faixa configurada da "
                f"fonte (ver 'instrument.ranges' em app_config.yaml)."
            )
        if selected.name == self._active_range_name:
            return
        # Trocar de faixa com a saída ligada pode causar uma queda momentânea
        # de tensão na placa sob teste (comportamento do próprio instrumento,
        # não deste driver) — normalmente só ocorre em passos intermediários
        # de uma sequência multi-step que atravessa duas faixas. Usa o cache
        # local (self._output_on) em vez de sondar OUTPut:STATe? por SCPI:
        # essa sondagem rodaria a cada passo de uma sequência multi-step só
        # para decidir se loga um aviso, um round-trip serial desnecessário
        # no caminho sensível a tempo do ensaio.
        if self._output_on:
            _logger.warning(
                "Trocando faixa da fonte (%s -> %s) com a saída LIGADA — pode haver "
                "queda momentânea de tensão na placa sob teste.",
                self._active_range_name,
                selected.name,
            )
        self.set_voltage_range(selected.name)
        self._active_range_name = selected.name

    def measure_voltage(self) -> float:
        return self.scpi.query_float("MEASure:VOLTage:DC?")

    def measure_current(self) -> float:
        return self.scpi.query_float("MEASure:CURRent:DC?")

    def apply(self, volts: float, amps: float) -> None:
        """APPLy — define tensão e corrente em um único comando."""
        self._ensure_range(volts, amps)
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
