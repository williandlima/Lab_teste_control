"""Montagem dos dados de relatório a partir da camada de repositórios.

Os três formatos de saída (Excel/Word/PDF) consomem a mesma `ReportData`,
montada uma única vez aqui — assim nenhum dos geradores faz SQL ou conhece
os repositories, e qualquer cálculo (ex. min/max das amostras) é feito em
um único lugar.
"""
from __future__ import annotations

import json
import statistics
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
class StepStats:
    """Estatísticas factuais de um passo/ciclo — informativo, nunca veredito.

    `voltage_out_of_range` conta amostras fora da faixa de referência
    (voltage_min/voltage_max) e `current_over_limit` as que passaram do
    current_max. São contagens descritivas para o operador/qualidade
    analisarem; a decisão PASS/FAIL continua exclusivamente manual.
    """
    step_index: int
    sample_count: int
    voltage_mean: float
    voltage_std: float
    voltage_min: float
    voltage_max: float
    current_mean: float
    current_std: float
    current_min: float
    current_max: float
    voltage_out_of_range: int
    current_over_limit: int


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
    step_stats: list[StepStats]


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
        step_stats=_compute_step_stats(samples, config_snapshot),
    )


def _compute_step_stats(
    samples: list[MonitoredSample], config_snapshot: dict
) -> list[StepStats]:
    """Agrega estatísticas descritivas por passo (step_index) das amostras."""
    v_min_ref = config_snapshot.get("voltage_min")
    v_max_ref = config_snapshot.get("voltage_max")
    i_max_ref = config_snapshot.get("current_max")

    by_step: dict[int, list[MonitoredSample]] = {}
    for sample in samples:
        by_step.setdefault(sample.step_index, []).append(sample)

    stats: list[StepStats] = []
    for step_index in sorted(by_step):
        group = by_step[step_index]
        volts = [s.voltage_measured for s in group]
        amps = [s.current_measured for s in group]
        stats.append(
            StepStats(
                step_index=step_index,
                sample_count=len(group),
                voltage_mean=statistics.fmean(volts),
                voltage_std=statistics.pstdev(volts) if len(volts) > 1 else 0.0,
                voltage_min=min(volts),
                voltage_max=max(volts),
                current_mean=statistics.fmean(amps),
                current_std=statistics.pstdev(amps) if len(amps) > 1 else 0.0,
                current_min=min(amps),
                current_max=max(amps),
                voltage_out_of_range=sum(
                    1
                    for v in volts
                    if (v_min_ref is not None and v < v_min_ref)
                    or (v_max_ref is not None and v > v_max_ref)
                ),
                current_over_limit=sum(
                    1 for a in amps if i_max_ref is not None and a > i_max_ref
                ),
            )
        )
    return stats
