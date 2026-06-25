"""Carregamento da configuração externa (config/config.yaml).

Nenhum caminho de rede, host SMTP ou limiar de dias deve ser hardcoded em
outros módulos deste pacote: tudo passa por este loader.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "config.yaml"


@dataclass(frozen=True)
class PlanilhasConfig:
    equipamentos_path: Path
    equipamentos_sheet: str | None
    emprestimos_path: Path
    emprestimos_sheet: str | None
    pasta_temp: Path


@dataclass(frozen=True)
class ColunasEquipamentosConfig:
    codigo: str
    descricao: str
    responsavel_padrao: str
    local_padrao: str
    status: str
    proxima_calibracao: str | None
    email_responsavel: str | None


@dataclass(frozen=True)
class ColunasEmprestimosConfig:
    data_hora: str
    codigo: str
    tipo_evento: str
    responsavel: str
    destino: str
    previsao_devolucao: str
    observacao: str


@dataclass(frozen=True)
class LimiaresDiasConfig:
    verde: int
    amarelo: int
    urgente: int


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    usar_tls: bool
    usuario: str | None
    senha: str | None
    remetente: str
    destinatario_admin: str


@dataclass(frozen=True)
class EstadoConfig:
    estado_alertas_path: Path
    log_path: Path
    relatorio_html_path: Path


@dataclass(frozen=True)
class AppConfig:
    planilhas: PlanilhasConfig
    colunas_equipamentos: ColunasEquipamentosConfig
    colunas_emprestimos: ColunasEmprestimosConfig
    status_ignorados: tuple[str, ...]
    limiares_dias: LimiaresDiasConfig
    smtp: SmtpConfig
    estado: EstadoConfig
    raw: dict[str, Any] = field(repr=False, compare=False)


def _resolve_path(raw_path: str) -> Path:
    """Expande '~' e mantém caminhos de rede (UNC) intactos."""
    return Path(os.path.expanduser(raw_path))


def load_config(config_path: Path | None = None, create_dirs: bool = True) -> AppConfig:
    """Carrega e valida config.yaml, criando as pastas de estado/temp.

    Args:
        config_path: caminho alternativo para o YAML (uso em testes).
        create_dirs: se True, cria pasta_temp e a pasta do estado/log.
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    planilhas_raw = raw["planilhas"]
    pasta_temp = _resolve_path(planilhas_raw["pasta_temp"])
    planilhas = PlanilhasConfig(
        equipamentos_path=_resolve_path(planilhas_raw["equipamentos_path"]),
        equipamentos_sheet=planilhas_raw.get("equipamentos_sheet"),
        emprestimos_path=_resolve_path(planilhas_raw["emprestimos_path"]),
        emprestimos_sheet=planilhas_raw.get("emprestimos_sheet"),
        pasta_temp=pasta_temp,
    )

    cols_equip_raw = raw["colunas_equipamentos"]
    colunas_equipamentos = ColunasEquipamentosConfig(
        codigo=cols_equip_raw["codigo"],
        descricao=cols_equip_raw["descricao"],
        responsavel_padrao=cols_equip_raw["responsavel_padrao"],
        local_padrao=cols_equip_raw["local_padrao"],
        status=cols_equip_raw["status"],
        proxima_calibracao=cols_equip_raw.get("proxima_calibracao"),
        email_responsavel=cols_equip_raw.get("email_responsavel"),
    )

    cols_emp_raw = raw["colunas_emprestimos"]
    colunas_emprestimos = ColunasEmprestimosConfig(**cols_emp_raw)

    limiares_dias = LimiaresDiasConfig(**raw["limiares_dias"])

    smtp_raw = raw["smtp"]
    smtp = SmtpConfig(
        host=smtp_raw["host"],
        port=smtp_raw["port"],
        usar_tls=smtp_raw.get("usar_tls", False),
        usuario=smtp_raw.get("usuario"),
        senha=os.environ.get("CTRL_EQUIP_SMTP_SENHA") or smtp_raw.get("senha"),
        remetente=smtp_raw["remetente"],
        destinatario_admin=smtp_raw["destinatario_admin"],
    )

    estado_raw = raw["estado"]
    estado = EstadoConfig(
        estado_alertas_path=_resolve_path(estado_raw["estado_alertas_path"]),
        log_path=_resolve_path(estado_raw["log_path"]),
        relatorio_html_path=_resolve_path(estado_raw["relatorio_html_path"]),
    )

    if create_dirs:
        pasta_temp.mkdir(parents=True, exist_ok=True)
        estado.estado_alertas_path.parent.mkdir(parents=True, exist_ok=True)
        estado.log_path.parent.mkdir(parents=True, exist_ok=True)
        estado.relatorio_html_path.parent.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        planilhas=planilhas,
        colunas_equipamentos=colunas_equipamentos,
        colunas_emprestimos=colunas_emprestimos,
        status_ignorados=tuple(raw.get("status_ignorados", ())),
        limiares_dias=limiares_dias,
        smtp=smtp,
        estado=estado,
        raw=raw,
    )
