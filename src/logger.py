"""Configuração de logging estruturado, separado por módulo.

Cada subsistema grava em seu próprio arquivo rotativo, para que o log de
TX/RX serial (alto volume, nível DEBUG) nunca afogue o log geral da
aplicação nem o da state machine. Nada é acumulado sem limite em memória ou
em widget de UI: a tela só lê as últimas N linhas via um handler em buffer
separado (ver gui/widgets, que consome `UI_LOG_BUFFER`).
"""
from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LoggingConfig

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Buffer circular consumido pela GUI (ex. painel de log da main_window).
# Nunca usar QTextEdit sem limite: a UI lê só este deque, não o arquivo inteiro.
UI_LOG_BUFFER: deque[str] = deque(maxlen=200)


class _UiBufferHandler(logging.Handler):
    """Handler que só espelha as últimas N linhas para a GUI, sem I/O."""

    def __init__(self, buffer: deque[str]) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(self.format(record))


def _make_rotating_handler(
    log_path: Path, level: str, max_bytes: int, backup_count: int
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    return handler


def setup_logging(logging_cfg: LoggingConfig, logs_dir: Path) -> None:
    """Configura os loggers `app`, `serial_io` e `state_machine`.

    Idempotente: chamadas repetidas não duplicam handlers (útil em testes).
    """
    root_app_logger = logging.getLogger("app")
    if root_app_logger.handlers:
        return

    root_app_logger.setLevel(logging_cfg.level)
    root_app_logger.addHandler(
        _make_rotating_handler(
            logs_dir / "app.log",
            logging_cfg.level,
            logging_cfg.max_bytes,
            logging_cfg.backup_count,
        )
    )

    ui_handler = _UiBufferHandler(UI_LOG_BUFFER)
    ui_handler.setLevel(logging_cfg.level)
    ui_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root_app_logger.addHandler(ui_handler)

    serial_logger = logging.getLogger("serial_io")
    serial_logger.setLevel(logging_cfg.serial_io_level)
    serial_logger.addHandler(
        _make_rotating_handler(
            logs_dir / "serial_io.log",
            logging_cfg.serial_io_level,
            logging_cfg.max_bytes,
            logging_cfg.backup_count,
        )
    )

    state_machine_logger = logging.getLogger("state_machine")
    state_machine_logger.setLevel(logging_cfg.level)
    state_machine_logger.addHandler(
        _make_rotating_handler(
            logs_dir / "state_machine.log",
            logging_cfg.level,
            logging_cfg.max_bytes,
            logging_cfg.backup_count,
        )
    )
    state_machine_logger.addHandler(ui_handler)
