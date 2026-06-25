"""Ponto de entrada: o que o Task Scheduler do Windows chama todo dia de manhã.

Lê a planilha de equipamentos e o log de empréstimos (cópia local, nunca
edita os originais), calcula a situação de cada equipamento, compara com o
estado salvo no dia anterior e só manda e-mail para o que mudou de faixa de
calibração ou ficou atrasado hoje. Qualquer falha (planilha bloqueada, SMTP
fora do ar) é logada e o script termina sem travar — o Task Scheduler tenta
de novo no dia seguinte.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

from .classificar import classificar_calibracao
from .config import AppConfig, load_config
from .enviar_email import enviar_alertas
from .ler_emprestimos import ler_emprestimos
from .ler_planilha import ler_equipamentos
from .localizacao_atual import calcular_situacao_atual
from .modelos import AlertaCalibracao, AlertaEmprestimoAtrasado, Equipamento
from .relatorio_html import gerar_relatorio_html

logger = logging.getLogger("controle_equipamentos")


def _setup_logging(log_path: Path) -> None:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stdout))


def _carregar_estado_anterior(caminho: Path) -> dict[str, dict[str, object]]:
    if not caminho.exists():
        return {}
    with caminho.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _salvar_estado(caminho: Path, estado: dict[str, dict[str, object]]) -> None:
    with caminho.open("w", encoding="utf-8") as fh:
        json.dump(estado, fh, ensure_ascii=False, indent=2, sort_keys=True)


def _destinatario(equipamento: Equipamento, config: AppConfig) -> str:
    return equipamento.email_responsavel or config.smtp.destinatario_admin


def _executar(config: AppConfig, hoje: date | None = None) -> None:
    hoje = hoje or date.today()

    logger.info("Lendo planilha de equipamentos: %s", config.planilhas.equipamentos_path)
    equipamentos = ler_equipamentos(config)
    logger.info("%d equipamentos cadastrados", len(equipamentos))

    logger.info("Lendo log de empréstimos: %s", config.planilhas.emprestimos_path)
    eventos = ler_emprestimos(config)
    logger.info("%d eventos de empréstimo", len(eventos))

    situacoes = calcular_situacao_atual(equipamentos, eventos, hoje=hoje)

    ativos = [eq for eq in equipamentos if eq.status not in config.status_ignorados]
    faixas = {eq.codigo: classificar_calibracao(eq, config.limiares_dias, hoje=hoje) for eq in ativos}

    estado_anterior = _carregar_estado_anterior(config.estado.estado_alertas_path)

    alertas_calibracao: list[AlertaCalibracao] = []
    alertas_emprestimo: list[AlertaEmprestimoAtrasado] = []
    novo_estado: dict[str, dict[str, object]] = {}

    for equipamento in ativos:
        situacao = situacoes[equipamento.codigo]
        faixa = faixas[equipamento.codigo]
        anterior = estado_anterior.get(equipamento.codigo, {})

        if faixa.value != anterior.get("faixa"):
            alertas_calibracao.append(
                AlertaCalibracao(
                    codigo=equipamento.codigo,
                    descricao=equipamento.descricao,
                    faixa=faixa,
                    proxima_calibracao=equipamento.proxima_calibracao,
                    destinatario=_destinatario(equipamento, config),
                )
            )

        if situacao.atrasado and not anterior.get("atrasado", False):
            assert situacao.previsao_devolucao is not None
            alertas_emprestimo.append(
                AlertaEmprestimoAtrasado(
                    codigo=equipamento.codigo,
                    descricao=equipamento.descricao,
                    responsavel=situacao.responsavel_atual,
                    local=situacao.local_atual,
                    previsao_devolucao=situacao.previsao_devolucao,
                    destinatario=_destinatario(equipamento, config),
                )
            )

        novo_estado[equipamento.codigo] = {"faixa": faixa.value, "atrasado": situacao.atrasado}

    if alertas_calibracao or alertas_emprestimo:
        enviados = enviar_alertas(config, alertas_calibracao, alertas_emprestimo)
        logger.info(
            "%d alerta(s) de calibração, %d de empréstimo atrasado — %d e-mail(s) enviado(s)",
            len(alertas_calibracao),
            len(alertas_emprestimo),
            enviados,
        )
    else:
        logger.info("Nenhuma mudança de faixa ou atraso novo — nenhum e-mail enviado")

    _salvar_estado(config.estado.estado_alertas_path, novo_estado)

    relatorio = gerar_relatorio_html(ativos, situacoes, faixas, hoje=hoje)
    config.estado.relatorio_html_path.write_text(relatorio, encoding="utf-8")
    logger.info("Relatório HTML atualizado em %s", config.estado.relatorio_html_path)


def main() -> int:
    config = load_config()
    _setup_logging(config.estado.log_path)
    try:
        _executar(config)
    except Exception:
        logger.exception("Execução falhou — tentando de novo na próxima vez agendada")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
