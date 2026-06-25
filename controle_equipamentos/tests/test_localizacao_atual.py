from datetime import date, datetime

from controle_equipamentos.localizacao_atual import calcular_situacao_atual
from controle_equipamentos.modelos import Equipamento, EventoEmprestimo, TipoEvento

HOJE = date(2026, 6, 25)


def _equipamento(codigo: str) -> Equipamento:
    return Equipamento(
        codigo=codigo,
        descricao="Multímetro",
        responsavel_padrao="Laboratório",
        local_padrao="Sala 1",
        status="Em uso",
        proxima_calibracao=None,
        email_responsavel=None,
    )


def _evento(
    codigo: str,
    tipo: TipoEvento,
    dia: str,
    responsavel: str = "João",
    destino: str = "Setor Y",
    previsao: date | None = None,
) -> EventoEmprestimo:
    return EventoEmprestimo(
        data_hora=datetime.strptime(dia, "%d/%m/%Y %H:%M"),
        codigo=codigo,
        tipo_evento=tipo,
        responsavel=responsavel,
        destino=destino,
        previsao_devolucao=previsao,
        observacao="",
    )


def test_sem_eventos_usa_padrao_da_planilha():
    situacoes = calcular_situacao_atual([_equipamento("A1")], [], hoje=HOJE)
    situacao = situacoes["A1"]
    assert situacao.emprestado is False
    assert situacao.responsavel_atual == "Laboratório"
    assert situacao.local_atual == "Sala 1"


def test_retirada_sem_devolucao_fica_emprestado():
    eventos = [_evento("A1", TipoEvento.RETIRADA, "01/06/2026 09:00", previsao=date(2026, 6, 30))]
    situacoes = calcular_situacao_atual([_equipamento("A1")], eventos, hoje=HOJE)
    situacao = situacoes["A1"]
    assert situacao.emprestado is True
    assert situacao.responsavel_atual == "João"
    assert situacao.local_atual == "Setor Y"
    assert situacao.atrasado is False


def test_devolucao_depois_da_retirada_volta_ao_padrao():
    eventos = [
        _evento("A1", TipoEvento.RETIRADA, "01/06/2026 09:00"),
        _evento("A1", TipoEvento.DEVOLUCAO, "10/06/2026 09:00"),
    ]
    situacoes = calcular_situacao_atual([_equipamento("A1")], eventos, hoje=HOJE)
    assert situacoes["A1"].emprestado is False


def test_emprestimo_atrasado_quando_previsao_passou():
    eventos = [_evento("A1", TipoEvento.RETIRADA, "01/06/2026 09:00", previsao=date(2026, 6, 10))]
    situacoes = calcular_situacao_atual([_equipamento("A1")], eventos, hoje=HOJE)
    assert situacoes["A1"].atrasado is True


def test_so_considera_o_ultimo_ciclo_de_retirada():
    eventos = [
        _evento("A1", TipoEvento.RETIRADA, "01/06/2026 09:00", responsavel="Maria"),
        _evento("A1", TipoEvento.DEVOLUCAO, "05/06/2026 09:00"),
        _evento("A1", TipoEvento.RETIRADA, "10/06/2026 09:00", responsavel="Carlos", destino="Setor Z"),
    ]
    situacoes = calcular_situacao_atual([_equipamento("A1")], eventos, hoje=HOJE)
    situacao = situacoes["A1"]
    assert situacao.responsavel_atual == "Carlos"
    assert situacao.local_atual == "Setor Z"
