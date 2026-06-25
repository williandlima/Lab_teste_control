"""Monta e envia o e-mail HTML consolidado de alertas, via SMTP interno."""
from __future__ import annotations

import smtplib
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import AppConfig
from .modelos import AlertaCalibracao, AlertaEmprestimoAtrasado, FaixaCalibracao

_COR_FAIXA = {
    FaixaCalibracao.VERDE: "#2e7d32",
    FaixaCalibracao.AMARELO: "#f9a825",
    FaixaCalibracao.URGENTE: "#ef6c00",
    FaixaCalibracao.VERMELHO: "#c62828",
    FaixaCalibracao.SEM_DATA: "#757575",
}


def agrupar_por_destinatario(
    alertas_calibracao: list[AlertaCalibracao],
    alertas_emprestimo: list[AlertaEmprestimoAtrasado],
) -> dict[str, tuple[list[AlertaCalibracao], list[AlertaEmprestimoAtrasado]]]:
    """Agrupa os dois tipos de alerta por destinatário (1 e-mail por pessoa)."""
    grupos: dict[str, tuple[list[AlertaCalibracao], list[AlertaEmprestimoAtrasado]]] = defaultdict(
        lambda: ([], [])
    )
    for alerta in alertas_calibracao:
        grupos[alerta.destinatario][0].append(alerta)
    for alerta in alertas_emprestimo:
        grupos[alerta.destinatario][1].append(alerta)
    return dict(grupos)


def _linha_calibracao(alerta: AlertaCalibracao) -> str:
    cor = _COR_FAIXA[alerta.faixa]
    data_texto = alerta.proxima_calibracao.strftime("%d/%m/%Y") if alerta.proxima_calibracao else "—"
    return (
        "<tr>"
        f"<td>{alerta.codigo}</td>"
        f"<td>{alerta.descricao}</td>"
        f"<td style='color:{cor};font-weight:bold'>{alerta.faixa.value}</td>"
        f"<td>{data_texto}</td>"
        "</tr>"
    )


def _linha_emprestimo(alerta: AlertaEmprestimoAtrasado) -> str:
    return (
        "<tr>"
        f"<td>{alerta.codigo}</td>"
        f"<td>{alerta.descricao}</td>"
        f"<td>{alerta.responsavel}</td>"
        f"<td>{alerta.local}</td>"
        f"<td>{alerta.previsao_devolucao.strftime('%d/%m/%Y')}</td>"
        "</tr>"
    )


def montar_corpo_html(
    alertas_calibracao: list[AlertaCalibracao],
    alertas_emprestimo: list[AlertaEmprestimoAtrasado],
) -> str:
    blocos = ["<html><body style='font-family:Arial,sans-serif;font-size:13px'>"]

    if alertas_calibracao:
        linhas = "".join(_linha_calibracao(alerta) for alerta in alertas_calibracao)
        blocos.append(
            "<h3>Calibração</h3>"
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<tr><th>Código</th><th>Descrição</th><th>Situação</th><th>Próxima calibração</th></tr>"
            f"{linhas}</table>"
        )

    if alertas_emprestimo:
        linhas = "".join(_linha_emprestimo(alerta) for alerta in alertas_emprestimo)
        blocos.append(
            "<h3>Empréstimo atrasado</h3>"
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<tr><th>Código</th><th>Descrição</th><th>Responsável</th><th>Local</th>"
            "<th>Previsão de devolução</th></tr>"
            f"{linhas}</table>"
        )

    blocos.append("</body></html>")
    return "".join(blocos)


def enviar_email(config: AppConfig, destinatario: str, assunto: str, corpo_html: str) -> None:
    mensagem = MIMEMultipart("alternative")
    mensagem["Subject"] = assunto
    mensagem["From"] = config.smtp.remetente
    mensagem["To"] = destinatario
    if destinatario != config.smtp.destinatario_admin:
        mensagem["Cc"] = config.smtp.destinatario_admin
    mensagem.attach(MIMEText(corpo_html, "html", "utf-8"))

    destinatarios = [destinatario]
    if destinatario != config.smtp.destinatario_admin:
        destinatarios.append(config.smtp.destinatario_admin)

    with smtplib.SMTP(config.smtp.host, config.smtp.port, timeout=30) as smtp:
        if config.smtp.usar_tls:
            smtp.starttls()
        if config.smtp.usuario:
            smtp.login(config.smtp.usuario, config.smtp.senha or "")
        smtp.sendmail(config.smtp.remetente, destinatarios, mensagem.as_string())


def enviar_alertas(
    config: AppConfig,
    alertas_calibracao: list[AlertaCalibracao],
    alertas_emprestimo: list[AlertaEmprestimoAtrasado],
) -> int:
    """Envia um e-mail consolidado por destinatário. Devolve quantos foram enviados."""
    grupos = agrupar_por_destinatario(alertas_calibracao, alertas_emprestimo)
    for destinatario, (calibracao, emprestimo) in grupos.items():
        corpo = montar_corpo_html(calibracao, emprestimo)
        enviar_email(config, destinatario, "Controle de Equipamentos — alertas do dia", corpo)
    return len(grupos)
