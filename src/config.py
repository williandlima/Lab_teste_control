"""Carregamento da configuração externa (config/app_config.yaml).

Nenhum parâmetro operacional (portas, caminhos, branding) deve ser hardcoded
em outros módulos: tudo passa por este loader, que resolve `~` para a pasta
do usuário Windows atual e garante que as pastas de dados existam.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "app_config.yaml"


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path
    database_path: Path
    logs_dir: Path
    exports_dir: Path


@dataclass(frozen=True)
class SerialConfig:
    port: str | None
    vid: int | None
    pid: int | None
    baudrate: int
    bytesize: int
    parity: str
    stopbits: int
    timeout_s: float
    write_timeout_s: float
    force_dtr_high: bool
    # Handshake: a E363x usa DTR/DSR. Num cabo de 3 fios sem jumper DTR-DSR a
    # fonte segura as respostas (timeout). Erguer RTS/DTR pelo PC ajuda quando
    # o cabo cruza essas linhas; mantidos configuráveis para não ficar preso a
    # uma única fiação. (ver drivers/serial_driver.py:connect)
    force_rts_high: bool = True
    rtscts: bool = False
    dsrdtr: bool = False
    # Modo demonstração: usa uma fonte simulada em vez da porta COM real, para
    # rodar o fluxo completo sem hardware conectado (ver simulated_serial.py).
    simulate: bool = False


@dataclass(frozen=True)
class ReconnectionConfig:
    max_retries: int
    backoff_base_s: float
    backoff_multiplier: float
    heartbeat_interval_s: float


@dataclass(frozen=True)
class TestDefaultsConfig:
    polling_rate_hz: float
    stabilization_timeout_s: float
    stabilization_tolerance_v: float
    monitoring_consecutive_failures_limit: int
    sample_batch_size: int
    sample_batch_interval_s: float
    live_buffer_maxlen: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    serial_io_level: str
    max_bytes: int
    backup_count: int
    ui_log_buffer_lines: int


@dataclass(frozen=True)
class BrandingConfig:
    company_name: str
    logo_path: Path
    color_primary_navy: str
    color_secondary_navy: str
    color_accent_orange: str
    color_accent_orange_hover: str
    color_text_on_navy: str
    color_pass: str
    color_fail: str
    color_warning: str


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig
    serial: SerialConfig
    reconnection: ReconnectionConfig
    test_defaults: TestDefaultsConfig
    logging: LoggingConfig
    branding: BrandingConfig
    raw: dict[str, Any] = field(repr=False, compare=False)


def _resolve_user_path(raw_path: str) -> Path:
    """Expande '~' para a pasta do usuário Windows/POSIX atual."""
    return Path(os.path.expanduser(raw_path)).resolve()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(config_path: Path | None = None, create_dirs: bool = True) -> AppConfig:
    """Carrega e valida a configuração externa, criando as pastas de dados.

    Args:
        config_path: caminho alternativo para o YAML (uso em testes).
        create_dirs: se True, cria data_dir/db/logs/exports no primeiro acesso.
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    paths_raw = raw["paths"]
    data_dir = _resolve_user_path(paths_raw["data_dir"])
    db_dir = data_dir / paths_raw["database_subdir"]
    logs_dir = data_dir / paths_raw["logs_subdir"]
    exports_dir = data_dir / paths_raw["exports_subdir"]
    database_path = db_dir / paths_raw["database_filename"]

    if create_dirs:
        for directory in (data_dir, db_dir, logs_dir, exports_dir):
            directory.mkdir(parents=True, exist_ok=True)

    serial_raw = raw["serial"]
    serial = SerialConfig(
        port=serial_raw.get("port"),
        vid=serial_raw.get("vid"),
        pid=serial_raw.get("pid"),
        baudrate=serial_raw["baudrate"],
        bytesize=serial_raw["bytesize"],
        parity=serial_raw["parity"],
        stopbits=serial_raw["stopbits"],
        timeout_s=serial_raw["timeout_s"],
        write_timeout_s=serial_raw["write_timeout_s"],
        force_dtr_high=serial_raw["force_dtr_high"],
        force_rts_high=serial_raw.get("force_rts_high", True),
        rtscts=serial_raw.get("rtscts", False),
        dsrdtr=serial_raw.get("dsrdtr", False),
        simulate=serial_raw.get("simulate", False),
    )

    reconnection = ReconnectionConfig(**raw["reconnection"])
    test_defaults = TestDefaultsConfig(**raw["test_defaults"])
    logging_cfg = LoggingConfig(**raw["logging"])

    branding_raw = raw["branding"]
    branding = BrandingConfig(
        company_name=branding_raw["company_name"],
        logo_path=_project_root() / branding_raw["logo_path"],
        color_primary_navy=branding_raw["color_primary_navy"],
        color_secondary_navy=branding_raw["color_secondary_navy"],
        color_accent_orange=branding_raw["color_accent_orange"],
        color_accent_orange_hover=branding_raw["color_accent_orange_hover"],
        color_text_on_navy=branding_raw["color_text_on_navy"],
        color_pass=branding_raw["color_pass"],
        color_fail=branding_raw["color_fail"],
        color_warning=branding_raw["color_warning"],
    )

    return AppConfig(
        paths=PathsConfig(
            data_dir=data_dir,
            database_path=database_path,
            logs_dir=logs_dir,
            exports_dir=exports_dir,
        ),
        serial=serial,
        reconnection=reconnection,
        test_defaults=test_defaults,
        logging=logging_cfg,
        branding=branding,
        raw=raw,
    )
