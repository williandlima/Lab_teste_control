"""Gera o relatório HTML estático (bônus): situação do dia, sem precisar de e-mail."""
from __future__ import annotations

from datetime import date

from .modelos import Equipamento, FaixaCalibracao, SituacaoAtual

_COR_FAIXA = {
    FaixaCalibracao.VERDE: "#2e7d32",
    FaixaCalibracao.AMARELO: "#f9a825",
    FaixaCalibracao.URGENTE: "#ef6c00",
    FaixaCalibracao.VERMELHO: "#c62828",
    FaixaCalibracao.SEM_DATA: "#757575",
}


def gerar_relatorio_html(
    equipamentos: list[Equipamento],
    situacoes: dict[str, SituacaoAtual],
    faixas: dict[str, FaixaCalibracao],
    hoje: date | None = None,
) -> str:
    hoje = hoje or date.today()
    linhas = []
    for equipamento in equipamentos:
        situacao = situacoes[equipamento.codigo]
        faixa = faixas[equipamento.codigo]
        cor = _COR_FAIXA[faixa]
        proxima = (
            equipamento.proxima_calibracao.strftime("%d/%m/%Y")
            if equipamento.proxima_calibracao
            else "—"
        )
        atraso_texto = "Sim" if situacao.atrasado else "Não"
        previsao = (
            situacao.previsao_devolucao.strftime("%d/%m/%Y") if situacao.previsao_devolucao else "—"
        )
        linhas.append(
            "<tr>"
            f"<td>{equipamento.codigo}</td>"
            f"<td>{equipamento.descricao}</td>"
            f"<td>{situacao.responsavel_atual}</td>"
            f"<td>{situacao.local_atual}</td>"
            f"<td style='color:{cor};font-weight:bold'>{faixa.value}</td>"
            f"<td>{proxima}</td>"
            f"<td>{atraso_texto}</td>"
            f"<td>{previsao}</td>"
            "</tr>"
        )

    return (
        "<html><body style='font-family:Arial,sans-serif;font-size:13px'>"
        f"<h2>Controle de Equipamentos — situação em {hoje.strftime('%d/%m/%Y')}</h2>"
        "<table border='1' cellpadding='6' cellspacing='0'>"
        "<tr><th>Código</th><th>Descrição</th><th>Responsável atual</th><th>Local atual</th>"
        "<th>Calibração</th><th>Próxima calibração</th><th>Empréstimo atrasado</th>"
        "<th>Previsão de devolução</th></tr>"
        f"{''.join(linhas)}</table></body></html>"
    )
