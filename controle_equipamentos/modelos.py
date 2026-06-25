"""Dataclasses compartilhadas entre os módulos de leitura, cálculo e e-mail."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class TipoEvento(str, Enum):
    RETIRADA = "Retirada"
    DEVOLUCAO = "Devolução"


@dataclass(frozen=True)
class Equipamento:
    codigo: str
    descricao: str
    responsavel_padrao: str
    local_padrao: str
    status: str
    proxima_calibracao: date | None
    email_responsavel: str | None


@dataclass(frozen=True)
class EventoEmprestimo:
    data_hora: datetime
    codigo: str
    tipo_evento: TipoEvento
    responsavel: str
    destino: str
    previsao_devolucao: date | None
    observacao: str


@dataclass(frozen=True)
class SituacaoAtual:
    codigo: str
    responsavel_atual: str
    local_atual: str
    emprestado: bool
    data_retirada: datetime | None
    previsao_devolucao: date | None
    atrasado: bool


class FaixaCalibracao(str, Enum):
    VERDE = "Verde"
    AMARELO = "Amarelo"
    URGENTE = "Urgente"
    VERMELHO = "Vermelho"
    SEM_DATA = "Sem data"


@dataclass(frozen=True)
class AlertaCalibracao:
    codigo: str
    descricao: str
    faixa: FaixaCalibracao
    proxima_calibracao: date | None
    destinatario: str


@dataclass(frozen=True)
class AlertaEmprestimoAtrasado:
    codigo: str
    descricao: str
    responsavel: str
    local: str
    previsao_devolucao: date
    destinatario: str
