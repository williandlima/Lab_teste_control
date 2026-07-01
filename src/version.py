"""Versão do software, exibida na Tela 1 e gravada nos relatórios.

Lida automaticamente de pyproject.toml — o único lugar onde o número
de versão precisa ser alterado. Fallback para importlib.metadata quando
o pacote estiver instalado (PyInstaller ou pip install -e .).
"""
from __future__ import annotations

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version

    APP_VERSION: str = _pkg_version("fct-avibras")
except Exception:
    import re
    from pathlib import Path

    _m = re.search(
        r'^version\s*=\s*"([^"]+)"',
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    APP_VERSION = _m.group(1) if _m else "0.0.0-dev"
