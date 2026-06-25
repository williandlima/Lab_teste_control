"""Testes da política de buffer circular + persistência em lote (seção 10)."""
from __future__ import annotations

from core.sampling_buffer import Sample, SamplingBuffer


def _sample(i: int) -> Sample:
    return Sample(timestamp=float(i), step_index=0, voltage=12.0 + i * 0.01, current=1.0)


def test_live_buffer_respects_maxlen() -> None:
    buffer = SamplingBuffer(live_buffer_maxlen=3, batch_size=100, batch_interval_s=999, on_flush=lambda batch: None)
    for i in range(10):
        buffer.add_sample(_sample(i))
    snapshot = buffer.live_snapshot()
    assert len(snapshot) == 3
    assert [s.timestamp for s in snapshot] == [7.0, 8.0, 9.0]


def test_flush_triggers_at_batch_size() -> None:
    flushed_batches: list[list[Sample]] = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100, batch_size=3, batch_interval_s=999, on_flush=flushed_batches.append
    )
    for i in range(5):
        buffer.add_sample(_sample(i))
    assert len(flushed_batches) == 1
    assert len(flushed_batches[0]) == 3


def test_flush_is_noop_when_pending_empty() -> None:
    flushed_batches: list[list[Sample]] = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100, batch_size=10, batch_interval_s=999, on_flush=flushed_batches.append
    )
    buffer.flush()
    assert flushed_batches == []


def test_explicit_flush_persists_remaining_pending_samples() -> None:
    flushed_batches: list[list[Sample]] = []
    buffer = SamplingBuffer(
        live_buffer_maxlen=100, batch_size=100, batch_interval_s=999, on_flush=flushed_batches.append
    )
    buffer.add_sample(_sample(0))
    buffer.add_sample(_sample(1))
    assert flushed_batches == []
    buffer.flush()
    assert len(flushed_batches) == 1
    assert len(flushed_batches[0]) == 2


def test_decimate_returns_same_list_when_under_limit() -> None:
    samples = [_sample(i) for i in range(5)]
    assert SamplingBuffer.decimate(samples, max_points=10) == samples


def test_decimate_aggregates_by_window_average() -> None:
    samples = [_sample(i) for i in range(10)]
    decimated = SamplingBuffer.decimate(samples, max_points=5)
    assert len(decimated) <= 5
    assert all(11.9 <= s.voltage <= 12.1 for s in decimated)
