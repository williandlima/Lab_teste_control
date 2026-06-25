"""Smoke test da GUI: garante que a janela e o cabeçalho montam sem erro.

Não dirige interação completa — apenas constrói a árvore de widgets (offscreen)
para travar regressões de wiring (sinais/slots, import, logo, seletor de porta).
Roda com QT_QPA_PLATFORM=offscreen, sem display real.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from config import load_config
from database.database import Database

pytest.importorskip("PySide6")


@pytest.fixture()
def app_config():
    # create_dirs=False: não suja o ~/LabTest da máquina ao rodar os testes.
    return load_config(create_dirs=False)


def test_header_bar_shows_logo_and_port_selector(qtbot, app_config) -> None:
    from gui.widgets.header_bar import HeaderBar

    header = HeaderBar(app_config.branding)
    qtbot.addWidget(header)

    # A logo da empresa precisa aparecer (arquivo existe em assets/branding).
    assert app_config.branding.logo_path.exists()
    assert header.logo_label.pixmap() is not None and not header.logo_label.pixmap().isNull()

    # O seletor de porta sempre tem ao menos a opção "Automático".
    assert header.port_combo.count() >= 1
    assert header.selected_port() == ""  # default = automático


def test_main_window_builds_full_flow(qtbot, app_config, tmp_path: Path) -> None:
    from gui.main_window import MainWindow

    db = Database(tmp_path / "smoke.db")
    db.connect()
    window = MainWindow(app_config, db)
    qtbot.addWidget(window)

    # Quatro etapas no stack: Cadastro, Parâmetros, Monitoramento, Avaliação.
    assert window.stack.count() == 4
    # O cabeçalho de marca/conexão está presente e acima do stack.
    assert window.header is not None
    db.close()
