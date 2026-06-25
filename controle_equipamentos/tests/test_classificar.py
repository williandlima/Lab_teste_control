from datetime import date, timedelta

from controle_equipamentos.classificar import classificar_calibracao
from controle_equipamentos.config import LimiaresDiasConfig
from controle_equipamentos.modelos import Equipamento, FaixaCalibracao

HOJE = date(2026, 6, 25)
LIMIARES = LimiaresDiasConfig(verde=90, amarelo=30, urgente=0)


def _equipamento(proxima_calibracao: date | None = None, status: str = "") -> Equipamento:
    return Equipamento(
        codigo="A1",
        descricao="Multímetro",
        responsavel_padrao="Setor X",
        local_padrao="Sala 1",
        status=status,
        proxima_calibracao=proxima_calibracao,
        email_responsavel=None,
    )


def test_verde_quando_calibracao_esta_longe():
    equipamento = _equipamento(HOJE + timedelta(days=200))
    assert classificar_calibracao(equipamento, LIMIARES, hoje=HOJE) is FaixaCalibracao.VERDE


def test_amarelo_entre_30_e_90_dias():
    equipamento = _equipamento(HOJE + timedelta(days=60))
    assert classificar_calibracao(equipamento, LIMIARES, hoje=HOJE) is FaixaCalibracao.AMARELO


def test_urgente_entre_0_e_30_dias():
    equipamento = _equipamento(HOJE + timedelta(days=10))
    assert classificar_calibracao(equipamento, LIMIARES, hoje=HOJE) is FaixaCalibracao.URGENTE


def test_vermelho_quando_vencida():
    equipamento = _equipamento(HOJE - timedelta(days=1))
    assert classificar_calibracao(equipamento, LIMIARES, hoje=HOJE) is FaixaCalibracao.VERMELHO


def test_fallback_por_status_quando_sem_data():
    assert (
        classificar_calibracao(_equipamento(None, status="Calibração Vencida"), LIMIARES, hoje=HOJE)
        is FaixaCalibracao.VERMELHO
    )
    assert (
        classificar_calibracao(_equipamento(None, status="Aguardando Calibração"), LIMIARES, hoje=HOJE)
        is FaixaCalibracao.URGENTE
    )
    assert (
        classificar_calibracao(_equipamento(None, status="Em uso"), LIMIARES, hoje=HOJE)
        is FaixaCalibracao.SEM_DATA
    )
