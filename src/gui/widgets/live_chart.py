"""Gráfico de tendência de tensão/corrente, com limites como referência visual.

Os limites (min/max) são SEMPRE linhas-guia — nunca disparam avaliação
automática (seção 3.3). Para sessões longas, o chamador deve passar os
dados já decimados (`SamplingBuffer.decimate`) para este widget não tentar
desenhar centenas de milhares de pontos.
"""
from __future__ import annotations

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets

from core.sampling_buffer import Sample


class LiveChart(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._voltage_series = QtCharts.QLineSeries(name="Tensão (V)")
        self._current_series = QtCharts.QLineSeries(name="Corrente (A)")
        self._voltage_min_series = QtCharts.QLineSeries(name="V mín (ref.)")
        self._voltage_max_series = QtCharts.QLineSeries(name="V máx (ref.)")
        for guide_series in (self._voltage_min_series, self._voltage_max_series):
            pen = guide_series.pen()
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            guide_series.setPen(pen)

        self._chart = QtCharts.QChart()
        self._chart.addSeries(self._voltage_series)
        self._chart.addSeries(self._voltage_min_series)
        self._chart.addSeries(self._voltage_max_series)
        self._chart.addSeries(self._current_series)
        self._chart.legend().setVisible(True)
        self._chart.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#0A1F44")))
        self._chart.setTitleBrush(QtGui.QBrush(QtGui.QColor("#F5F7FA")))

        self._axis_x = QtCharts.QValueAxis()
        self._axis_x.setTitleText("Tempo (s)")
        self._axis_voltage = QtCharts.QValueAxis()
        self._axis_voltage.setTitleText("Tensão (V)")
        self._axis_current = QtCharts.QValueAxis()
        self._axis_current.setTitleText("Corrente (A)")

        self._chart.addAxis(self._axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(self._axis_voltage, QtCore.Qt.AlignmentFlag.AlignLeft)
        self._chart.addAxis(self._axis_current, QtCore.Qt.AlignmentFlag.AlignRight)

        for series in (self._voltage_series, self._voltage_min_series, self._voltage_max_series):
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_voltage)
        self._current_series.attachAxis(self._axis_x)
        self._current_series.attachAxis(self._axis_current)

        chart_view = QtCharts.QChartView(self._chart)
        chart_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(chart_view)

        self._t0: float | None = None

    def set_voltage_limits(self, voltage_min: float, voltage_max: float, duration_s: float) -> None:
        self._voltage_min_series.replace([QtCore.QPointF(0, voltage_min), QtCore.QPointF(duration_s, voltage_min)])
        self._voltage_max_series.replace([QtCore.QPointF(0, voltage_max), QtCore.QPointF(duration_s, voltage_max)])
        self._axis_x.setRange(0, max(duration_s, 1.0))
        margin = max(0.5, (voltage_max - voltage_min) * 0.2)
        self._axis_voltage.setRange(voltage_min - margin, voltage_max + margin)

    def set_current_range(self, current_max: float) -> None:
        self._axis_current.setRange(0, max(current_max * 1.2, 0.1))

    def update_samples(self, samples: list[Sample]) -> None:
        if not samples:
            return
        if self._t0 is None:
            self._t0 = samples[0].timestamp

        voltage_points = [QtCore.QPointF(s.timestamp - self._t0, s.voltage) for s in samples]
        current_points = [QtCore.QPointF(s.timestamp - self._t0, s.current) for s in samples]
        self._voltage_series.replace(voltage_points)
        self._current_series.replace(current_points)

    def clear(self) -> None:
        self._t0 = None
        self._voltage_series.clear()
        self._current_series.clear()
