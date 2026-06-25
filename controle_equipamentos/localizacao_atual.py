"""Calcula responsável/local atual de cada equipamento a partir do log de empréstimos.

Localização e responsável nunca são editados diretamente — são derivados do
último evento de Retirada que ainda não tem uma Devolução depois dele. Sem
nenhum evento, vale o padrão cadastrado na planilha de equipamentos.
"""
from __future__ import annotations

from datetime import date

from .modelos import Equipamento, EventoEmprestimo, SituacaoAtual, TipoEvento


def calcular_situacao_atual(
    equipamentos: list[Equipamento],
    eventos: list[EventoEmprestimo],
    hoje: date | None = None,
) -> dict[str, SituacaoAtual]:
    """Devolve a situação atual de cada equipamento cadastrado, por código.

    `eventos` deve estar ordenado por data/hora crescente (ler_emprestimos.py
    já garante isso). Para cada código, o último evento manda: uma Retirada
    sem Devolução posterior deixa o equipamento "emprestado"; qualquer outra
    sequência (terminando em Devolução, ou sem eventos) deixa no padrão.
    """
    hoje = hoje or date.today()

    eventos_por_codigo: dict[str, list[EventoEmprestimo]] = {}
    for evento in eventos:
        eventos_por_codigo.setdefault(evento.codigo, []).append(evento)

    situacoes: dict[str, SituacaoAtual] = {}
    for equipamento in equipamentos:
        ultima_retirada_aberta: EventoEmprestimo | None = None
        for evento in eventos_por_codigo.get(equipamento.codigo, []):
            if evento.tipo_evento is TipoEvento.RETIRADA:
                ultima_retirada_aberta = evento
            elif evento.tipo_evento is TipoEvento.DEVOLUCAO:
                ultima_retirada_aberta = None

        if ultima_retirada_aberta is None:
            situacoes[equipamento.codigo] = SituacaoAtual(
                codigo=equipamento.codigo,
                responsavel_atual=equipamento.responsavel_padrao,
                local_atual=equipamento.local_padrao,
                emprestado=False,
                data_retirada=None,
                previsao_devolucao=None,
                atrasado=False,
            )
            continue

        previsao = ultima_retirada_aberta.previsao_devolucao
        atrasado = previsao is not None and previsao < hoje
        situacoes[equipamento.codigo] = SituacaoAtual(
            codigo=equipamento.codigo,
            responsavel_atual=ultima_retirada_aberta.responsavel,
            local_atual=ultima_retirada_aberta.destino,
            emprestado=True,
            data_retirada=ultima_retirada_aberta.data_hora,
            previsao_devolucao=previsao,
            atrasado=atrasado,
        )

    return situacoes
