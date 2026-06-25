# Controle de Equipamentos — Empréstimo, Localização, Responsável e Alerta de Calibração

Pacote independente do app FCT (`src/`). Não tem servidor, não tem banco de
dados novo: a planilha de equipamentos continua sendo a fonte de cadastro, e
um log de empréstimos só de inserção (`emprestimos.xlsx`) registra quem
pegou/devolveu cada equipamento. Um script (`main.py`) lê os dois, calcula a
situação do dia e manda e-mail só quando algo muda — chamado uma vez por dia
pelo Task Scheduler do Windows.

Ver o design completo na thread/issue que originou este pacote. Resumo do
fluxo: ler planilhas (cópia local, nunca edita os originais) → calcular
responsável/local atual de cada equipamento a partir do log de empréstimos →
classificar a urgência de calibração → comparar com o estado do dia anterior
→ mandar e-mail consolidado por responsável só para o que mudou → atualizar
o relatório HTML estático.

## Antes de colocar em produção — confirmar com a TI/usuário

Estes pontos têm valores-placeholder em `config/config.yaml` (marcados com
`# AJUSTAR`) que **precisam** ser substituídos pelos valores reais:

1. **Caminhos de rede** (`planilhas.equipamentos_path`,
   `planilhas.emprestimos_path`) — caminho UNC real das duas planilhas.
2. **Coluna "Próxima Calibração"** — se a planilha de equipamentos ainda não
   tiver essa coluna de data, deixe `colunas_equipamentos.proxima_calibracao:
   null` em `config.yaml`. O script cai automaticamente no modo sem
   antecedência (alerta só quando o texto da coluna de status mudar para algo
   com "vencida"/"aguardando" — ver `classificar.py`).
3. **SMTP interno** (`smtp.host`, `smtp.port`, `smtp.usar_tls`,
   `smtp.usuario`) — confirmar com a TI se exige autenticação. Se sim,
   preencha `smtp.usuario` e defina a senha pela variável de ambiente
   `CTRL_EQUIP_SMTP_SENHA` (nunca em texto puro no YAML).
4. **Remetente/destinatário admin** (`smtp.remetente`,
   `smtp.destinatario_admin`) — endereços reais.
5. **Onde roda** — máquina do usuário ou servidor da TI; só muda o agendador,
   não o código.
6. **Prazo de devolução obrigatório?** — hoje o script só avisa atraso de
   empréstimo quando a coluna "Previsão de devolução" está preenchida na
   Retirada. Se ficar em branco, esse equipamento nunca entra no alerta de
   atraso (mas continua aparecendo no relatório HTML).

## Planilhas esperadas

### Equipamentos (cadastro existente, só leitura)

Colunas configuráveis em `colunas_equipamentos` (`config/config.yaml`):
código, descrição, responsável padrão, local padrão, status,
"Próxima Calibração" (data, opcional) e e-mail do responsável (opcional —
sem isso o alerta cai no `destinatario_admin`).

### `emprestimos.xlsx` (log só de inserção — nunca editar uma linha existente)

| Coluna | Exemplo |
|---|---|
| Data/Hora | 25/06/2026 09:14 |
| Código do equipamento | A2080024 |
| Tipo de evento | Retirada / Devolução |
| Responsável | nome de quem pegou |
| Destino/Local | setor ou sala onde vai ficar |
| Previsão de devolução | 30/06/2026 (só preenche na Retirada) |
| Observação | opcional |

Hoje a pessoa digita a linha direto na planilha. "Quem está com o quê agora"
é sempre o último evento de Retirada sem Devolução depois — nunca uma edição
em cima do que já existia (ver `localizacao_atual.py`).

## Rodar manualmente

```bash
pip install -r requirements.txt   # já cobre openpyxl/PyYAML, sem dependência nova
python -m controle_equipamentos.main
```

Roda sempre como módulo (`-m controle_equipamentos.main`), nunca
`python main.py` direto — os imports internos são relativos ao pacote.

## Agendar no Task Scheduler (Windows)

- **Programa**: caminho do `python.exe` da venv do projeto.
- **Argumentos**: `-m controle_equipamentos.main`
- **Iniciar em**: a raiz do repositório (onde está `pyproject.toml`).
- **Disparo**: diário, ex. 7h.

## Arquivos gerados (não versionados)

Caminhos definidos em `estado` no `config.yaml` (por padrão em
`~/ControleEquipamentos/`):

- `estado_alertas.json` — memória do que já foi avisado, para não repetir o
  mesmo e-mail todo dia.
- `log.txt` — histórico de execuções (sucesso/erro).
- `relatorio.html` — situação do dia (calibração + quem está com cada
  equipamento + empréstimos atrasados), atualizado a cada execução.

## Testes

```bash
pytest controle_equipamentos/tests
```

Cobre a lógica pura (classificação de calibração, cálculo de
responsável/local atual a partir do log de empréstimos, agrupamento de
alertas por e-mail) e a leitura das planilhas com arquivos `.xlsx` de
exemplo gerados em memória — sem precisar de planilha real nem SMTP.

## Estrutura

```
controle_equipamentos/
├── main.py                 # orquestra tudo, chamado pelo Task Scheduler
├── config.py / config/config.yaml   # caminhos, SMTP, limiares de dias
├── modelos.py               # dataclasses compartilhadas
├── io_utils.py               # cópia segura antes de ler (evita travar a planilha de rede)
├── ler_planilha.py           # lê a planilha de equipamentos
├── ler_emprestimos.py        # lê emprestimos.xlsx
├── localizacao_atual.py      # cruza os dois: responsável/local atual por equipamento
├── classificar.py             # dias restantes -> faixa verde/amarelo/urgente/vermelho
├── enviar_email.py            # monta o HTML e manda pelo SMTP
├── relatorio_html.py          # relatório estático (bônus, sem precisar de e-mail)
└── tests/                     # pytest, sem I/O real
```
