# Prepara o ambiente de desenvolvimento: cria a venv (se não existir) e
# instala as dependências de requirements.txt. Uso: .\scripts\setup_env.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path ".venv")) {
    Write-Host "Criando ambiente virtual em .venv..."
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Ambiente pronto."
Write-Host "No VSCode: Ctrl+Shift+P -> 'Python: Select Interpreter' -> escolha .venv\Scripts\python.exe"
