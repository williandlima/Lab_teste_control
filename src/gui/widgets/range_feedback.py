"""Feedback visual de faixa V/A da fonte, ANTES de qualquer comando SCPI.

Sem isto, o único jeito do operador descobrir que um setpoint não cabe na
faixa configurada (ou na faixa que ele forçou manualmente) é o "SCPI error
-222: Data out of range" depois de clicar em "Ligar saída"/"Salvar e
continuar". A parte pura (`evaluate_range_fit`) espelha exatamente a mesma
lógica de `PowerSupplyE363x._ensure_range`, mas sem I/O -- por isso é
testável sem Qt e sem porta serial, e reutilizável nos dois lugares que
pedem V/A ao operador (Saída manual e Parâmetros do ensaio).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6 import QtGui, QtWidgets

from config import VoltageRange
from hardware.power_supply import PowerSupplyE363x

# Mesma paleta de branding.color_warning/color_fail (app_config.yaml) --
# hardcoded aqui como nos demais widgets (status_badge.py) para não amarrar
# este helper puro a um QWidget com acesso a BrandingConfig.
_COLOR_WARNING = "#F1C40F"
_COLOR_FAIL = "#E74C3C"


class RangeFitState(str, Enum):
    OK = "OK"
    # Não cabe na faixa que o operador forçou manualmente, mas caberia em outra.
    OUT_OF_FORCED_RANGE = "OUT_OF_FORCED_RANGE"
    # Não cabe em NENHUMA faixa configurada (forçada ou não) -- vai falhar de
    # qualquer forma, mesmo com seleção automática.
    OUT_OF_ALL_RANGES = "OUT_OF_ALL_RANGES"


@dataclass(frozen=True)
class RangeFitResult:
    state: RangeFitState
    message: str  # "" quando OK


def evaluate_range_fit(
    volts: float,
    amps: float,
    ranges: tuple[VoltageRange, ...],
    forced_range_name: str | None = None,
) -> RangeFitResult:
    """Classifica volts/amps contra `ranges`, replicando `_ensure_range`.

    Sem faixas configuradas, sempre OK (mesmo comportamento de
    `_ensure_range` com `ranges=()`: gerenciamento desligado).
    """
    if not ranges:
        return RangeFitResult(RangeFitState.OK, "")

    if forced_range_name is not None:
        forced = next((r for r in ranges if r.name == forced_range_name), None)
        fits_forced = forced is not None and volts <= forced.max_voltage and amps <= forced.max_current
        if fits_forced:
            return RangeFitResult(RangeFitState.OK, "")
        fitting = PowerSupplyE363x.find_fitting_range(volts, amps, ranges)
        if fitting is not None:
            return RangeFitResult(
                RangeFitState.OUT_OF_FORCED_RANGE,
                f"{volts:.2f} V / {amps:.3f} A não cabe na faixa forçada "
                f"'{forced_range_name}'. Caberia em '{fitting.name}' "
                f"(até {fitting.max_voltage:.2f} V / {fitting.max_current:.3f} A).",
            )
        return RangeFitResult(
            RangeFitState.OUT_OF_ALL_RANGES,
            f"{volts:.2f} V / {amps:.3f} A não cabe em nenhuma faixa configurada da "
            f"fonte (nem na faixa forçada '{forced_range_name}').",
        )

    fitting = PowerSupplyE363x.find_fitting_range(volts, amps, ranges)
    if fitting is not None:
        return RangeFitResult(RangeFitState.OK, "")
    widest = max(ranges, key=lambda r: r.max_voltage)
    return RangeFitResult(
        RangeFitState.OUT_OF_ALL_RANGES,
        f"{volts:.2f} V / {amps:.3f} A não cabe em nenhuma faixa configurada da fonte "
        f"(máx. suportado: {widest.max_voltage:.2f} V / {widest.max_current:.3f} A).",
    )


_SPIN_STYLE_BY_STATE = {
    RangeFitState.OK: "",
    RangeFitState.OUT_OF_FORCED_RANGE: f"border: 2px solid {_COLOR_WARNING};",
    RangeFitState.OUT_OF_ALL_RANGES: f"border: 2px solid {_COLOR_FAIL};",
}


def apply_spin_feedback(spin: QtWidgets.QAbstractSpinBox, result: RangeFitResult) -> None:
    spin.setStyleSheet(_SPIN_STYLE_BY_STATE[result.state])
    spin.setToolTip(result.message)


def apply_table_item_feedback(item: QtWidgets.QTableWidgetItem, result: RangeFitResult) -> None:
    if result.state is RangeFitState.OK:
        item.setBackground(QtGui.QBrush())
        item.setToolTip("")
        return
    color = _COLOR_WARNING if result.state is RangeFitState.OUT_OF_FORCED_RANGE else _COLOR_FAIL
    item.setBackground(QtGui.QBrush(QtGui.QColor(color)))
    item.setToolTip(result.message)
