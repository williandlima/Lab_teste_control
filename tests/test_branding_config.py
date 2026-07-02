"""Testa o carregamento de branding.logo_header_path (variante da logo para
o cabeçalho navy da GUI -- ver gui/widgets/header_bar.py e a issue real de
contraste/caixa branca que motivou essa variante)."""
from __future__ import annotations

from pathlib import Path

from config import load_config


def test_shipped_config_resolves_logo_header_path() -> None:
    app_config = load_config(create_dirs=False)

    assert app_config.branding.logo_header_path is not None
    assert app_config.branding.logo_header_path.exists()
    assert app_config.branding.logo_header_path != app_config.branding.logo_path


def test_logo_header_path_is_none_when_not_configured(tmp_path: Path) -> None:
    """Sem `logo_header_path` no YAML, o campo fica None -- header_bar.py cai
    para logo_path (comportamento de antes desta opção, sem quebrar nada)."""
    import yaml

    from config import load_config as _load_config

    shipped = Path(__file__).resolve().parent.parent / "config" / "app_config.yaml"
    raw = yaml.safe_load(shipped.read_text(encoding="utf-8"))
    del raw["branding"]["logo_header_path"]
    custom_config = tmp_path / "app_config.yaml"
    custom_config.write_text(yaml.dump(raw), encoding="utf-8")

    app_config = _load_config(config_path=custom_config, create_dirs=False)

    assert app_config.branding.logo_header_path is None
