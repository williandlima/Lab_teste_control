"""Máquina de estados do teste funcional (seção 3.3).

Importante: esta classe NÃO decide PASS/FAIL. Ela só controla a fonte,
monitora e persiste tensão/corrente. A avaliação é sempre manual,
registrada via `mark_evaluated()` depois que o operador observa os dados.

É deliberadamente independente de PySide6: `run()` é bloqueante e deve ser
chamado de dentro de um worker thread (QThread) pela camada de GUI — nunca
da thread principal. Os hooks `on_state_changed`/`on_sample`/`on_event` são
callbacks simples, não Qt Signals, para que esta classe seja testável com
pytest puro e instrumento mockado (tests/test_state_machine.py).

Diagrama de estados aprovado:

    Idle -> Initializing -> CheckingCommunication -> ConfiguringSource
    -> ApplyingVoltage -> Stabilizing -> Monitoring -> ShuttingDownOutput
    -> AwaitingManualEvaluation -> Completed

Qualquer falha (CommError/Faulted/Aborted) também converge em
ShuttingDownOutput antes de chegar a AwaitingManualEvaluation — o
desligamento de saída é sempre tentado, mesmo em erro (failsafe).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from database.models import PowerStep
from drivers.exceptions import InstrumentCommunicationError
from hardware.power_supply import PowerSupplyE363x
from core.sampling_buffer import Sample, SamplingBuffer

_logger = logging.getLogger("state_machine")


class TestState(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    CHECKING_COMMUNICATION = "CHECKING_COMMUNICATION"
    CONFIGURING_SOURCE = "CONFIGURING_SOURCE"
    APPLYING_VOLTAGE = "APPLYING_VOLTAGE"
    STABILIZING = "STABILIZING"
    MONITORING = "MONITORING"
    SHUTTING_DOWN_OUTPUT = "SHUTTING_DOWN_OUTPUT"
    AWAITING_MANUAL_EVALUATION = "AWAITING_MANUAL_EVALUATION"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    COMM_ERROR = "COMM_ERROR"
    FAULTED = "FAULTED"


# Estados terminais possíveis para o retorno de run() / _finish().
_TERMINATION_STATES = (
    TestState.COMPLETED,
    TestState.ABORTED,
    TestState.COMM_ERROR,
    TestState.FAULTED,
)


@dataclass(frozen=True)
class TestRunConfig:
    nominal_voltage: float
    voltage_min: float
    voltage_max: float
    current_max: float
    test_duration_s: float
    power_sequence: list[PowerStep]
    polling_rate_hz: float
    stabilization_timeout_s: float
    stabilization_tolerance_v: float
    monitoring_consecutive_failures_limit: int
    # Intervalo entre capturas GRAVADAS (s). 0 = grava toda leitura. Distinto da
    # taxa de polling (display): evita overdata no relatório em ensaios longos.
    capture_interval_s: float = 0.0

    def steps(self) -> list[PowerStep]:
        """Sequência efetiva: usa power_sequence se houver, senão 1 passo único."""
        if self.power_sequence:
            return self.power_sequence
        return [PowerStep(self.nominal_voltage, self.current_max, self.test_duration_s)]


class TestStateMachine:
    def __init__(
        self,
        instrument: PowerSupplyE363x,
        sampling_buffer: SamplingBuffer,
        config: TestRunConfig,
        on_state_changed: Callable[[TestState], None] = lambda state: None,
        on_sample: Callable[[Sample], None] = lambda sample: None,
        on_event: Callable[[str, str], None] = lambda level, message: None,
    ) -> None:
        self._instrument = instrument
        self._buffer = sampling_buffer
        self._config = config
        self._on_state_changed = on_state_changed
        self._on_sample = on_sample
        self._on_event = on_event
        self._abort_requested = threading.Event()
        self._state = TestState.IDLE
        self._termination_reason: TestState | None = None

    @property
    def state(self) -> TestState:
        return self._state

    @property
    def termination_reason(self) -> TestState | None:
        return self._termination_reason

    def request_abort(self) -> None:
        """Thread-safe: chamado da GUI thread para cancelar um teste em curso."""
        self._abort_requested.set()

    def _set_state(self, state: TestState) -> None:
        self._state = state
        self._on_event("INFO", f"Estado: {state.value}")
        self._on_state_changed(state)
        _logger.info("Transição de estado: %s", state.value)

    def run(self) -> TestState:
        """Executa o fluxo completo de teste. Bloqueante — chamar em worker thread.

        O `except Exception` aqui é deliberado: este é o limite de segurança
        (failsafe) de todo o sistema. Qualquer falha não prevista nas etapas
        abaixo ainda precisa garantir OUTPUT OFF antes de propagar — por
        isso a captura é ampla, mas só neste ponto único e mais externo.
        """
        try:
            self._set_state(TestState.INITIALIZING)
            if not self._initialize():
                return self._finish(TestState.COMM_ERROR)

            self._set_state(TestState.CHECKING_COMMUNICATION)
            if not self._check_communication():
                return self._finish(TestState.COMM_ERROR)

            self._set_state(TestState.CONFIGURING_SOURCE)
            if not self._configure_source():
                return self._finish(TestState.FAULTED)

            self._set_state(TestState.APPLYING_VOLTAGE)
            if not self._apply_voltage():
                return self._finish(TestState.FAULTED)

            self._set_state(TestState.STABILIZING)
            stabilize_result = self._stabilize()
            if stabilize_result == "comm_error":
                return self._finish(TestState.COMM_ERROR)
            if stabilize_result == "timeout":
                return self._finish(TestState.FAULTED)
            if stabilize_result == "aborted":
                return self._finish(TestState.ABORTED)

            self._set_state(TestState.MONITORING)
            monitor_result = self._monitor()
            if monitor_result == "comm_error":
                return self._finish(TestState.COMM_ERROR)
            if monitor_result == "aborted":
                return self._finish(TestState.ABORTED)

            return self._finish(TestState.COMPLETED)
        except Exception as exc:
            self._on_event("ERROR", f"Falha inesperada na state machine: {exc}")
            _logger.exception("Falha inesperada na state machine")
            return self._finish(TestState.FAULTED)

    def mark_evaluated(self) -> None:
        """Transição final, disparada quando o operador salva a avaliação manual."""
        if self._state != TestState.AWAITING_MANUAL_EVALUATION:
            raise RuntimeError(
                "Avaliação só pode ser registrada após o teste atingir "
                f"AWAITING_MANUAL_EVALUATION (estado atual: {self._state.value})."
            )
        self._set_state(TestState.COMPLETED)

    # -- Etapas individuais -------------------------------------------------

    def _initialize(self) -> bool:
        try:
            self._instrument.connect()
            return True
        except InstrumentCommunicationError as exc:
            self._on_event("WARNING", f"Falha ao conectar, tentando reconexão: {exc}")
            return self._instrument.reconnect()

    def _check_communication(self) -> bool:
        """*IDN? + checagem de erros, com retry curto (instabilidade transitória)."""
        for attempt in range(1, 4):
            if self._instrument.heartbeat():
                return True
            self._on_event("WARNING", f"Heartbeat falhou (tentativa {attempt}/3).")
            time.sleep(1.0 * attempt)
        return False

    def _configure_source(self) -> bool:
        """Arma OVP/OCP nos limites configurados como proteção de hardware real
        (independente da regra de não-avaliação automática: isto é uma camada
        de segurança do instrumento, não um veredito de PASS/FAIL)."""
        for attempt in range(1, 3):
            try:
                self._instrument.set_overvoltage_protection(self._config.voltage_max)
                self._instrument.set_overcurrent_protection(self._config.current_max)
                return True
            except InstrumentCommunicationError as exc:
                self._on_event(
                    "WARNING", f"Erro ao configurar fonte (tentativa {attempt}/2): {exc}"
                )
        return False

    def _apply_voltage(self) -> bool:
        """Sem retry: aplicar tensão errada numa placa é mais grave que abortar."""
        first_step = self._config.steps()[0]
        try:
            self._instrument.apply(first_step.voltage, first_step.current)
            self._instrument.output_on()
            return True
        except InstrumentCommunicationError as exc:
            self._on_event("ERROR", f"Falha ao aplicar tensão: {exc}")
            return False

    def _stabilize(self) -> str:
        target_voltage = self._config.steps()[0].voltage
        poll_interval = 1.0 / self._config.polling_rate_hz
        deadline = time.monotonic() + self._config.stabilization_timeout_s

        while time.monotonic() < deadline:
            if self._abort_requested.is_set():
                return "aborted"
            try:
                measured = self._instrument.measure_voltage()
            except InstrumentCommunicationError as exc:
                self._on_event("ERROR", f"Erro de leitura durante estabilização: {exc}")
                return "comm_error"
            if abs(measured - target_voltage) <= self._config.stabilization_tolerance_v:
                return "stable"
            time.sleep(poll_interval)
        return "timeout"

    def _monitor(self) -> str:
        """Polling síncrono e pausado (seção 10): um comando por vez, nunca
        enfileirado, para não disparar -521 Input buffer overflow na fonte."""
        consecutive_failures = 0
        poll_interval = 1.0 / self._config.polling_rate_hz
        capture_interval = self._config.capture_interval_s
        last_capture_monotonic: float | None = None
        last_capture_step: int | None = None

        for step_index, step in enumerate(self._config.steps()):
            if step_index > 0:
                try:
                    self._instrument.apply(step.voltage, step.current)
                except InstrumentCommunicationError as exc:
                    self._on_event("ERROR", f"Falha ao aplicar passo {step_index}: {exc}")
                    return "comm_error"

            step_deadline = time.monotonic() + step.duration_s
            while time.monotonic() < step_deadline:
                if self._abort_requested.is_set():
                    return "aborted"

                loop_start = time.monotonic()
                try:
                    voltage = self._instrument.measure_voltage()
                    current = self._instrument.measure_current()
                except InstrumentCommunicationError as exc:
                    consecutive_failures += 1
                    self._on_event(
                        "WARNING",
                        f"Falha de leitura ({consecutive_failures}/"
                        f"{self._config.monitoring_consecutive_failures_limit}): {exc}",
                    )
                    if consecutive_failures >= self._config.monitoring_consecutive_failures_limit:
                        return "comm_error"
                    time.sleep(poll_interval)
                    continue

                consecutive_failures = 0
                sample = Sample(
                    timestamp=time.time(),
                    step_index=step_index,
                    voltage=voltage,
                    current=current,
                )
                # Display SEMPRE em tempo real; gravação só na taxa de captura
                # (evita overdata). Garante a 1ª amostra de cada ciclo gravada.
                self._on_sample(sample)
                if self._should_capture(loop_start, step_index, last_capture_monotonic, last_capture_step):
                    self._buffer.add_sample(sample)
                    last_capture_monotonic = loop_start
                    last_capture_step = step_index

                elapsed = time.monotonic() - loop_start
                time.sleep(max(0.0, poll_interval - elapsed))

        return "completed"

    def _should_capture(
        self,
        now_monotonic: float,
        step_index: int,
        last_capture_monotonic: float | None,
        last_capture_step: int | None,
    ) -> bool:
        """Decide se a amostra atual deve ser GRAVADA (não só exibida).

        Grava se: captura está desativada (intervalo <= 0, grava todas), é a
        primeira amostra, mudou de ciclo (garante 1 ponto por passo), ou já
        passou o intervalo de captura desde a última gravação.
        """
        if self._config.capture_interval_s <= 0:
            return True
        if last_capture_monotonic is None or step_index != last_capture_step:
            return True
        return (now_monotonic - last_capture_monotonic) >= self._config.capture_interval_s

    def _finish(self, termination_reason: TestState) -> TestState:
        self._termination_reason = termination_reason
        self._set_state(TestState.SHUTTING_DOWN_OUTPUT)
        self._safe_shutdown_output()
        self._buffer.flush()
        self._set_state(TestState.AWAITING_MANUAL_EVALUATION)
        return termination_reason

    def _safe_shutdown_output(self) -> None:
        """Failsafe: tentativa best-effort de desligar a saída, sempre."""
        try:
            self._instrument.output_off()
        except InstrumentCommunicationError as exc:
            self._on_event(
                "ERROR",
                f"Não foi possível confirmar desligamento da saída via SCPI: {exc}. "
                "Desligamento manual da fonte pode ser necessário.",
            )
