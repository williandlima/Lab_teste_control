"""Utilitário comum aos leitores de planilha: cópia segura antes de ler.

Ler direto do arquivo de rede que várias pessoas têm aberto no Excel corre o
risco de travar o arquivo ou ler no meio de uma gravação. Copiando primeiro
para uma pasta temporária local, a leitura sempre vê uma cópia consistente.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path


def copiar_para_temp(origem: Path, pasta_temp: Path) -> Path:
    pasta_temp.mkdir(parents=True, exist_ok=True)
    destino = pasta_temp / f"{int(time.time() * 1000)}_{origem.name}"
    shutil.copy2(origem, destino)
    return destino
