"""Garante a disciplina de versionamento: version.py == pyproject.toml.

A versão é exibida na Tela 1 e gravada nos relatórios (rastreabilidade), então
as duas fontes precisam andar juntas a cada evolução do software.
"""
from __future__ import annotations

import re
from pathlib import Path

from version import APP_VERSION


def test_app_version_matches_pyproject() -> None:
    root = Path(__file__).resolve().parent.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "version não encontrada em pyproject.toml"
    assert match.group(1) == APP_VERSION
