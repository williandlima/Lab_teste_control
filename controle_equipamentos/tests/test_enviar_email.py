from datetime import date

from controle_equipamentos.enviar_email import agrupar_por_destinatario, montar_corpo_html
from controle_equipamentos.modelos import AlertaCalibracao, AlertaEmprestimoAtrasado, FaixaCalibracao


def _alerta_calibracao(destinatario: str) -> AlertaCalibracao:
    return AlertaCalibracao(
        codigo="A1",
        descricao="Multímetro",
        faixa=FaixaCalibracao.VERMELHO,
        proxima_calibracao=date(2026, 1, 1),
        destinatario=destinatario,
    )


def _alerta_emprestimo(destinatario: str) -> AlertaEmprestimoAtrasado:
    return AlertaEmprestimoAtrasado(
        codigo="A2",
        descricao="Osciloscópio",
        responsavel="João",
        local="Setor Y",
        previsao_devolucao=date(2026, 6, 1),
        destinatario=destinatario,
    )


def test_agrupa_por_destinatario_mantendo_os_dois_tipos():
    grupos = agrupar_por_destinatario(
        [_alerta_calibracao("a@x.com")],
        [_alerta_emprestimo("a@x.com"), _alerta_emprestimo("b@x.com")],
    )

    assert set(grupos) == {"a@x.com", "b@x.com"}
    calibracao_a, emprestimo_a = grupos["a@x.com"]
    assert len(calibracao_a) == 1
    assert len(emprestimo_a) == 1
    calibracao_b, emprestimo_b = grupos["b@x.com"]
    assert calibracao_b == []
    assert len(emprestimo_b) == 1


def test_corpo_html_so_inclui_secoes_com_alertas():
    corpo_so_calibracao = montar_corpo_html([_alerta_calibracao("a@x.com")], [])
    assert "Calibração" in corpo_so_calibracao
    assert "Empréstimo atrasado" not in corpo_so_calibracao

    corpo_so_emprestimo = montar_corpo_html([], [_alerta_emprestimo("a@x.com")])
    assert "Empréstimo atrasado" in corpo_so_emprestimo
    assert "<h3>Calibração</h3>" not in corpo_so_emprestimo
