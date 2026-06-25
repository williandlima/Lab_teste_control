"""Ponto de entrada da aplicação FCT.

Carrega `config/app_config.yaml`, configura o logging, abre/migra o banco
SQLite e sobe a `MainWindow`. Nenhuma lógica de domínio mora aqui — só o
bootstrap (seção 2 da arquitetura).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from PySide6 import QtWidgets  # noqa: E402

import logger as logger_module  # noqa: E402
from config import load_config  # noqa: E402
from database.database import Database  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app_config = load_config()
    logger_module.setup_logging(app_config.logging, app_config.paths.logs_dir)

    database = Database(app_config.paths.database_path)
    database.connect()

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(app_config, database)
    window.showMaximized()

    exit_code = app.exec()
    database.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
