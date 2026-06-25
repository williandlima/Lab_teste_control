"""Montagem dos dados de relatório a partir da camada de repositórios.

Os três formatos de saída (Excel/Word/PDF) consomem a mesma `ReportData`,
montada uma única vez aqui — assim nenhum dos geradores faz SQL ou conhece
os repositories, e qualquer cálculo (ex. min/max das amostras) é feito em
um único lugar.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from database.models import (
    Board,
    Evaluation,
    EventLogEntry,
    MonitoredSample,
    Operator,
    TestSession,
)
from database.repositories import (
    BoardRepository,
    EvaluationRepository,
    EventLogRepository,
    MonitoredSampleRepository,
    OperatorRepository,
    TestSessionRepository,
)


@dataclass(frozen=True)
class ReportData:
    session: TestSession
    board: Board
    operator: Operator
    samples: list[MonitoredSample]
    evaluation: Evaluation | None
    events: list[EventLogEntry]
    config_snapshot: dict
    voltage_min_observed: float | None
    voltage_max_observed: float | None
    current_min_observed: float | None
    current_max_observed: float | None


def assemble_report_data(
    test_session_id: int,
    session_repo: TestSessionRepository,
    board_repo: BoardRepository,
    operator_repo: OperatorRepository,
    sample_repo: MonitoredSampleRepository,
    evaluation_repo: EvaluationRepository,
    event_repo: EventLogRepository,
) -> ReportData:
    """Reúne sessão + agregados num único objeto, pronto para os geradores."""
    session = session_repo.get(test_session_id)
    board = board_repo.get(session.board_id)
    operator = operator_repo.get(session.operator_id)
    samples = sample_repo.list_for_session(test_session_id)
    evaluation = evaluation_repo.get_for_session(test_session_id)
    events = event_repo.list_for_session(test_session_id)
    config_snapshot = json.loads(session.config_snapshot_json)

    voltages = [s.voltage_measured for s in samples]
    currents = [s.current_measured for s in samples]

    return ReportData(
        session=session,
        board=board,
        operator=operator,
        samples=samples,
        evaluation=evaluation,
        events=events,
        config_snapshot=config_snapshot,
        voltage_min_observed=min(voltages) if voltages else None,
        voltage_max_observed=max(voltages) if voltages else None,
        current_min_observed=min(currents) if currents else None,
        current_max_observed=max(currents) if currents else None,
    )
