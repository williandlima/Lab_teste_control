"""Modelos de dados (dataclasses), espelhando as tabelas de `migrations/`.

Não são modelos de ORM — são apenas a forma com que os repositories
devolvem dados para o resto da aplicação. Manter como dataclasses simples
evita amarrar o resto do app a uma lib de ORM específica.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TestSessionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    COMM_ERROR = "COMM_ERROR"
    FAULTED = "FAULTED"


class EvaluationResult(str, Enum):
    """Resultado SEMPRE escolhido manualmente pelo operador (seção 3.3)."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    OBSERVATION = "OBSERVATION"


@dataclass(frozen=True)
class Operator:
    id: int | None
    name: str
    created_at: str | None = None


@dataclass(frozen=True)
class Board:
    id: int | None
    code: str
    part_number: str
    revision: str
    created_at: str | None = None


@dataclass(frozen=True)
class PowerStep:
    voltage: float
    current: float
    duration_s: float


@dataclass(frozen=True)
class TestParameterConfig:
    id: int | None
    board_id: int | None
    name: str
    nominal_voltage: float
    voltage_min: float
    voltage_max: float
    current_max: float
    test_duration_s: float
    power_sequence: list[PowerStep]
    created_at: str | None = None


@dataclass(frozen=True)
class TestSession:
    id: int | None
    board_id: int
    serial_number: str
    operator_id: int
    test_parameter_config_id: int | None
    config_snapshot_json: str
    production_order: str | None
    observations: str | None
    status: TestSessionStatus
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class MonitoredSample:
    id: int | None
    test_session_id: int
    timestamp: str
    step_index: int
    voltage_measured: float
    current_measured: float


@dataclass(frozen=True)
class Evaluation:
    id: int | None
    test_session_id: int
    operator_id: int
    result: EvaluationResult
    comment: str | None
    evaluated_at: str | None = None


@dataclass(frozen=True)
class EventLogEntry:
    id: int | None
    test_session_id: int | None
    timestamp: str | None
    level: str
    source: str
    message: str
