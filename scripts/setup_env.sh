#!/usr/bin/env bash
# Prepara o ambiente de desenvolvimento: cria a venv (se não existir) e
# instala as dependências de requirements.txt. Uso: bash scripts/setup_env.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d ".venv" ]; then
    echo "Criando ambiente virtual em .venv..."
    python3 -m venv .venv
fi

./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo ""
echo "Ambiente pronto."
echo "No VSCode: Ctrl+Shift+P -> 'Python: Select Interpreter' -> escolha .venv/bin/python"
