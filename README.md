# Sistema FCT (Functional Circuit Test) — Avibras Aeroco

Sistema desktop de Teste Funcional para placas eletrônicas, controlando uma
fonte programável Keysight/Agilent E363x via SCPI sobre RS-232. O resultado
do teste (Aprovado/Reprovado/Observação) é **sempre** escolhido manualmente
pelo operador — o sistema nunca decide isso automaticamente.

## 1. Pré-requisitos

- **Python 3.10 ou 3.11** (`pyproject.toml` fixa `>=3.10,<3.12` — 3.12+ não é suportado).
- Windows é o ambiente alvo (caminhos como `~/LabTest` resolvem para a pasta
  do usuário Windows atual), mas o projeto também roda em Linux/Mac para
  desenvolvimento.
- Fonte Keysight/Agilent **E363x** conectada via adaptador USB-serial (FTDI),
  cabo 3 fios.

## 2. Instalação

```bash
git clone <url-do-repo>
cd wdlima

# Ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# Dependências
pip install -r requirements.txt
```

`requirements.txt` já traz tudo: PySide6 (GUI), pyserial, PyYAML,
openpyxl/python-docx/reportlab (relatórios) e pytest (testes).

## 3. Configurar o hardware

Edite `config/app_config.yaml`, seção `serial:`

```yaml
serial:
  port: null        # null = autodetecta pelo VID/PID abaixo; ou fixe ex. "COM3"
  vid: 0x0403       # VID do adaptador USB-serial (ajuste para o seu hardware real)
  pid: 0x6001       # PID do adaptador
  baudrate: 9600    # deve bater com o painel frontal da E363x
  stopbits: 2       # fixo — 1 causa erro de framing na E363x
```

⚠️ Esses valores **não são enviados** à fonte por software — baud, paridade e
bits são configurados manualmente no painel frontal do instrumento e os
valores aqui precisam refletir exatamente o que está configurado lá.

Outras seções relevantes do mesmo arquivo:

- `paths.data_dir`: onde o banco SQLite, logs e relatórios exportados são
  gravados (`~/LabTest` por padrão, criado automaticamente no primeiro acesso).
- `branding`: nome da empresa e logo usados nos relatórios — já vem
  preenchido com a identidade Avibras Aeroco.

## 4. Rodar os testes (opcional, mas recomendado)

```bash
pytest
```

Cobre drivers, protocolo SCPI, state machine, banco de dados e geração de
relatórios, sem precisar da fonte real conectada.

## 5. Executar o sistema

```bash
python main.py
```

Isso carrega a configuração, configura o logging, conecta/migra o banco
SQLite e abre a janela principal.

## 6. Fluxo de uso na GUI

1. **Cadastro** — informe código da placa, part number, revisão, número de
   série e operador.
2. **Parâmetros** — defina tensão nominal/mín/máx, corrente máxima, duração
   do teste (ou carregue uma configuração salva anteriormente para a mesma
   placa).
3. **Monitoramento** — acompanhe tensão/corrente em tempo real, badges de
   status (REMOTO/SAÍDA/PROTEÇÃO) e gráfico ao vivo. É possível abortar o
   teste manualmente.
4. **Avaliação manual** — ao final (sucesso, erro de comunicação ou
   abortado), revise o resumo e escolha Aprovado/Reprovado/Observação com
   comentário opcional.
5. Volta ao Cadastro, pronto para o próximo teste.

Os relatórios (Excel/Word/PDF) ficam em `~/LabTest/exports` e são gerados a
partir dos dados de cada sessão salva no banco.

## Estrutura do projeto

```
config/app_config.yaml   Configuração externa (paths, serial, branding etc.)
main.py                   Ponto de entrada da aplicação
src/
  core/                   State machine do teste, buffer de amostragem
  database/               Modelos, repositories e migrações SQLite
  drivers/                Protocolo SCPI e transporte serial
  hardware/               Driver específico da fonte E363x
  gui/                    Telas PySide6 (Cadastro → Parâmetros → Monitoramento → Avaliação)
  reports/                Geração de relatórios Excel/Word/PDF
tests/                    Suíte pytest
```
