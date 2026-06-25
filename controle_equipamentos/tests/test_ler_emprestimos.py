from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook

from controle_equipamentos.config import AppConfig, ColunasEmprestimosConfig, PlanilhasConfig
from controle_equipamentos.ler_emprestimos import ler_emprestimos
from controle_equipamentos.modelos import TipoEvento


def _config(emprestimos_path: Path, pasta_temp: Path) -> AppConfig:
    return AppConfig(
        planilhas=PlanilhasConfig(
            equipamentos_path=emprestimos_path,
            equipamentos_sheet=None,
            emprestimos_path=emprestimos_path,
            emprestimos_sheet=None,
            pasta_temp=pasta_temp,
        ),
        colunas_equipamentos=None,  # type: ignore[arg-type]
        colunas_emprestimos=ColunasEmprestimosConfig(
            data_hora="Data/Hora",
            codigo="Código do equipamento",
            tipo_evento="Tipo de evento",
            responsavel="Responsável",
            destino="Destino/Local",
            previsao_devolucao="Previsão de devolução",
            observacao="Observação",
        ),
        status_ignorados=(),
        limiares_dias=None,  # type: ignore[arg-type]
        smtp=None,  # type: ignore[arg-type]
        estado=None,  # type: ignore[arg-type]
        raw={},
    )


_CABECALHO = [
    "Data/Hora",
    "Código do equipamento",
    "Tipo de evento",
    "Responsável",
    "Destino/Local",
    "Previsão de devolução",
    "Observação",
]


def test_le_eventos_e_ordena_por_data(tmp_path: Path):
    caminho = tmp_path / "emprestimos.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(_CABECALHO)
    sheet.append([datetime(2026, 6, 10, 9, 0), "A1", "Devolução", "João", "Sala 1", None, ""])
    sheet.append([datetime(2026, 6, 1, 9, 0), "A1", "Retirada", "João", "Setor Y", date(2026, 6, 9), ""])
    workbook.save(caminho)

    eventos = ler_emprestimos(_config(caminho, tmp_path / "tmp"))

    assert len(eventos) == 2
    assert eventos[0].tipo_evento is TipoEvento.RETIRADA
    assert eventos[1].tipo_evento is TipoEvento.DEVOLUCAO
    assert eventos[0].data_hora < eventos[1].data_hora


def test_linha_sem_tipo_evento_reconhecido_e_ignorada(tmp_path: Path):
    caminho = tmp_path / "emprestimos.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(_CABECALHO)
    sheet.append([datetime(2026, 6, 1, 9, 0), "A1", "???", "João", "Setor Y", None, ""])
    workbook.save(caminho)

    eventos = ler_emprestimos(_config(caminho, tmp_path / "tmp"))

    assert eventos == []
