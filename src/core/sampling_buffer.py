"""Buffer circular de exibição + persistência em lote (seção 10).

Previne o crescimento ilimitado de memória em testes de longa duração:
- `_live`: `deque(maxlen=N)` só para o gráfico ao vivo — nunca a fonte de
  verdade dos dados.
- `_pending`: acumula amostras até atingir `batch_size` ou `batch_interval_s`,
  então dispara `on_flush` (tipicamente um `MonitoredSampleRepository.insert_batch`)
  — nunca um INSERT por amostra.

Esta classe não conhece SQLite nem PySide6: o callback `on_flush` é injetado
por quem a instancia (core/state_machine.py), mantendo-a testável isolada.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Sample:
    timestamp: float
    step_index: int
    voltage: float
    current: float


class SamplingBuffer:
    def __init__(
        self,
        live_buffer_maxlen: int,
        batch_size: int,
        batch_interval_s: float,
        on_flush: Callable[[list[Sample]], None],
    ) -> None:
        self._live: deque[Sample] = deque(maxlen=live_buffer_maxlen)
        self._pending: list[Sample] = []
        self._batch_size = batch_size
        self._batch_interval_s = batch_interval_s
        self._on_flush = on_flush
        self._last_flush_monotonic = time.monotonic()

    def add_sample(self, sample: Sample) -> None:
        """Adiciona ao buffer de exibição e decide se é hora de persistir."""
        self._live.append(sample)
        self._pending.append(sample)
        elapsed = time.monotonic() - self._last_flush_monotonic
        if len(self._pending) >= self._batch_size or elapsed >= self._batch_interval_s:
            self.flush()

    def flush(self) -> None:
        """Persiste o lote pendente. Deve ser chamado também ao final do teste,
        para não perder as últimas amostras que não completaram um lote."""
        self._last_flush_monotonic = time.monotonic()
        if not self._pending:
            return
        batch, self._pending = self._pending, []
        self._on_flush(batch)

    def live_snapshot(self) -> list[Sample]:
        """Cópia do buffer de exibição atual (para o gráfico ler sem lock)."""
        return list(self._live)

    @staticmethod
    def decimate(samples: list[Sample], max_points: int) -> list[Sample]:
        """Agrega por média em janelas, para exibir sessões de horas sem
        desenhar centenas de milhares de pontos. A granularidade completa
        permanece no banco — isto afeta só a apresentação."""
        if max_points <= 0 or len(samples) <= max_points:
            return samples

        window = math.ceil(len(samples) / max_points)
        decimated: list[Sample] = []
        for start in range(0, len(samples), window):
            chunk = samples[start : start + window]
            avg_voltage = sum(s.voltage for s in chunk) / len(chunk)
            avg_current = sum(s.current for s in chunk) / len(chunk)
            mid = chunk[len(chunk) // 2]
            decimated.append(
                Sample(
                    timestamp=mid.timestamp,
                    step_index=mid.step_index,
                    voltage=avg_voltage,
                    current=avg_current,
                )
            )
        return decimated
