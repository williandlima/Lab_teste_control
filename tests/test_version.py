"""Garante a disciplina de versionamento: pyproject.toml é a única fonte.

version.py lê a versão de pyproject.toml automaticamente — nunca mais
precisa ser editado manualmente. Estes testes verificam que o mecanismo
de leitura funciona e que o fallback "0.0.0-dev" não chegou a produção.
"""
from __future__ import annotations

import re
from pathlib import Path

from version import APP_VERSION


def test_app_version_matches_pyproject() -> None:
    """version.py deve refletir exatamente o que está em pyproject.toml."""
    root = Path(__file__).resolve().parent.parent
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, "campo 'version' não encontrado em pyproject.toml"
    pyproject_version = match.group(1)
    assert APP_VERSION == pyproject_version, (
        f"version.py retornou '{APP_VERSION}' mas pyproject.toml tem "
        f"'{pyproject_version}' — mecanismo de leitura pode ter falhado."
    )


def test_app_version_not_dev_fallback() -> None:
    """O placeholder de fallback não deve chegar a uma versão real."""
    assert APP_VERSION != "0.0.0-dev", (
        "version.py caiu no fallback de desenvolvimento — verifique se "
        "pyproject.toml existe e contém o campo 'version'."
    )
