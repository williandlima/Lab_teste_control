"""Classifica a urgência de calibração de cada equipamento.

Caminho principal (planilha com a coluna "Próxima Calibração" preenchida):
classifica pelos dias restantes, com antecedência configurável.

Fallback (planilha sem essa coluna, ou data vazia para aquele equipamento):
classifica só pelo texto da coluna de status — sem antecedência, mas ainda
dá pra alertar quando o status virar "vencida"/"aguardando".
"""
from __future__ import annotations

from datetime import date

from .config import LimiaresDiasConfig
from .modelos import Equipamento, FaixaCalibracao


def classificar_calibracao(
    equipamento: Equipamento,
    limiares: LimiaresDiasConfig,
    hoje: date | None = None,
) -> FaixaCalibracao:
    hoje = hoje or date.today()

    if equipamento.proxima_calibracao is not None:
        dias_restantes = (equipamento.proxima_calibracao - hoje).days
        if dias_restantes < limiares.urgente:
            return FaixaCalibracao.VERMELHO
        if dias_restantes <= limiares.amarelo:
            return FaixaCalibracao.URGENTE
        if dias_restantes <= limiares.verde:
            return FaixaCalibracao.AMARELO
        return FaixaCalibracao.VERDE

    status_normalizado = equipamento.status.casefold()
    if "vencid" in status_normalizado:
        return FaixaCalibracao.VERMELHO
    if "aguardando" in status_normalizado:
        return FaixaCalibracao.URGENTE
    return FaixaCalibracao.SEM_DATA
