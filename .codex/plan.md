# Plano de criação do projeto F1

## 1. Objetivo

Construir um projeto de engenharia de dados em Python para consultar, validar, transformar e persistir dados históricos da Fórmula 1 disponibilizados pela API OpenF1. O projeto deve ser executável localmente, reproduzível, testável e documentado.

## 2. Premissas e limites

- A fonte inicial será `https://api.openf1.org/v1/`.
- O primeiro escopo usará dados históricos gratuitos, sem autenticação. Dados em tempo real exigem assinatura e ficam fora do MVP.
- A API retorna normalmente listas JSON; campos podem estar ausentes ou nulos e a disponibilidade varia por sessão e endpoint.
- `meeting_key` representa uma etapa e `session_key` uma sessão. As consultas devem descobrir esses identificadores por `/meetings` e `/sessions`, sem fixar valores de exemplo no fluxo de produção.
- O destino de armazenamento ainda não foi definido. A primeira entrega deve manter essa escolha configurável e registrar a decisão antes de implementar a persistência definitiva.
- Este plano não fixa uma versão de Python: definir e validar a versão suportada antes de criar `.python-version`, `pyproject.toml` e a configuração do Ruff.

## 3. Escopo inicial (MVP)

1. Consultar etapas e sessões por ano, com filtros básicos.
2. Selecionar uma sessão e coletar dados relacionados. Para começar, priorizar `/drivers`, `/laps`, `/session_result`, `/starting_grid` e `/stints`; adicionar clima (`/weather`) quando fizer sentido para a análise.
3. Validar os registros recebidos, normalizar datas em UTC e preservar os identificadores da OpenF1.
4. Persistir os dados brutos e/ou processados no destino escolhido, com reexecução segura e rastreável.
5. Disponibilizar uma execução local pela raiz do repositório, logs operacionais, testes automatizados e documentação.

Ficam para etapas posteriores: telemetria de alta frequência (`/car_data`, `/location`), rádio, dados em tempo real, dashboards, processamento distribuído e orquestração em nuvem. Esses itens dependem de volume, custo, destino e objetivo analítico definidos.

## 4. Organização proposta

Usar o layout `src/`, com pacote importável `f1` e módulos criados apenas quando necessários:

```text
src/f1/
├── config.py
├── ingestion/       # cliente OpenF1 e consultas à API
├── transformations/ # normalização e regras de domínio
├── validation/      # contratos e verificações de qualidade
├── storage/         # adaptador do destino aprovado
└── services/        # coordenação do fluxo de coleta
tests/
├── unit/
└── integration/
docs/
```

Manter regras de transformação e validação independentes de HTTP e armazenamento. Evitar criar camadas ou diretórios vazios sem uma responsabilidade concreta.

## 5. Etapas de execução

### Etapa 1 — Definição e bootstrap

- Confirmar o caso de uso prioritário, granularidade, recorte inicial de temporadas/sessões e destino de dados.
- Definir a versão de Python compatível e registrá-la em `.python-version` e `pyproject.toml`.
- Inicializar Poetry 2.x, configurar `.venv` no projeto e declarar dependências nos grupos apropriados (`dev`, `test`, `docs`).
- Criar estrutura `src/f1/`, `.gitignore`, `.env.example`, README e configuração inicial do Ruff.
- Gerar e versionar `poetry.lock` pelo Poetry, nunca editando-o manualmente.

**Pronto quando:** ambiente é instalável com Poetry, pacote é importável e metadados passam em `poetry check`.

### Etapa 2 — Contratos e cliente da API

- Definir contratos de entrada e saída para os endpoints selecionados: campos usados, tipos, nulabilidade, chaves, granularidade, unidades e timezone.
- Implementar cliente HTTP isolado com timeout, tratamento explícito de erros e retries limitados com backoff/jitter apenas para falhas transitórias.
- Montar parâmetros de filtro com codificação segura, incluindo operadores de comparação; não concatenar entrada sem codificação na URL.
- Consultar `/meetings` e `/sessions` para descobrir chaves e registrar endpoint, filtros e intervalo consultado nos metadados da execução.
- Tratar respostas vazias, campos ausentes e limites da fonte sem converter falha em sucesso vazio.

**Pronto quando:** chamadas e erros são exercitáveis com respostas determinísticas simuladas, sem depender da API em testes unitários.

### Etapa 3 — Ingestão, transformação e qualidade

- Implementar fluxo explícito: leitura → validação de entrada → transformação → validação de saída → gravação.
- Preservar chaves de origem (`meeting_key`, `session_key`, `driver_number`) e timestamps; normalizar datas para UTC sem perder o valor original quando necessário.
- Definir regras para nulos, campos extras/ausentes, tipos inesperados, duplicatas e registros rejeitados; falhas críticas devem ser acionáveis e rejeições contabilizadas.
- Manter transformações determinísticas e sem I/O oculto; trabalhar com amostras representativas antes de avaliar volumes maiores.

**Pronto quando:** contratos e regras principais têm cobertura unitária de sucesso, limites e entradas inválidas.

### Etapa 4 — Persistência e reprocessamento

- Escolher e documentar o destino e o formato após confirmação dos requisitos de consulta e volume.
- Definir chave natural, unidade de reprocessamento e política idempotente (por exemplo, upsert por chave ou substituição atômica de partição).
- Especificar comportamento para duplicatas, execução concorrente, falha parcial e reprocessamento de sessões antigas.
- Se houver watermark/checkpoint, atualizá-lo somente após confirmar a gravação. Garantir que escrita parcial não substitua resultado válido.

**Pronto quando:** reexecutar a mesma unidade não duplica nem corrompe dados e a recuperação após falha está documentada.

### Etapa 5 — Execução, observabilidade e segurança

- Oferecer comando de execução a partir da raiz do projeto, com parâmetros explícitos para ano, etapa/sessão e endpoints.
- Validar configuração cedo; não incluir credenciais reais. Manter `.env` fora do Git e `.env.example` apenas com nomes e valores fictícios/vazios.
- Registrar início/fim, identificador da execução, escopo consultado, contagens lidas/aceitas/rejeitadas/gravadas, duração e erros, sem gravar payloads completos ou segredos.
- Documentar limites da OpenF1 relevantes: dados históricos gratuitos, tempo real pago, disponibilidade variável e possíveis atrasos ou incompletude por endpoint.

**Pronto quando:** uma execução pode ser diagnosticada pelos logs e falhas de configuração ou fonte terminam com mensagem clara.

### Etapa 6 — Qualidade, CI e documentação

- Configurar Ruff para lint, formato e imports, habilitando ao menos `E`, `F`, `I`, `B` e `UP` (mais regras adequadas ao projeto).
- Configurar pytest e pytest-cov; atingir pelo menos 50% de cobertura unitária sem exclusões artificiais. Manter testes de integração separados e sem dependência na suíte unitária padrão.
- Adicionar CI para instalação com Poetry, `poetry check`, lint, verificação de formato, testes e build da documentação.
- Criar documentação MkDocs Material com páginas úteis para início rápido, arquitetura, desenvolvimento e testes; declarar `docs_dir` e navegação coerentes em `mkdocs.yml`.
- Manter README com objetivo, requisitos, instalação, configuração, execução e limitações.

**Pronto quando:** documentação compila e os comandos de qualidade definidos no `SKILL.md` passam.

## 6. Testes e critérios de aceite

- Testes unitários determinísticos para construção de consultas, validação, transformação, idempotência e tratamento de erros.
- Testes de integração opcionais, claramente identificados, para API ou destino real; não exigir credenciais externas na suíte padrão.
- Cobertura unitária mínima de 50% do pacote de produção.
- Ruff passa em lint, formato e imports; `poetry check` e `poetry run mkdocs build` terminam sem erros.
- Uma coleta histórica reproduzível gera dados válidos, registra contagens e pode ser repetida conforme a política de idempotência definida.
- Segredos não aparecem em código, logs, fixtures ou documentação.

## 7. Decisões pendentes antes da implementação completa

1. Qual análise ou produto será atendido primeiro (por exemplo, resultados por temporada, estratégia de pneus ou telemetria)?
2. Qual destino deve ser usado no MVP (arquivos locais, banco ou armazenamento em nuvem) e quais consultas ele precisa suportar?
3. Quais temporadas e endpoints formam o primeiro recorte? A proposta inicial deste plano é iniciar por sessões históricas com resultados, pilotos, voltas e stints.
4. A entrega deve incluir somente execução local ou também agendamento/CI de ingestão?

As respostas orientam o contrato de dados, a escolha do armazenamento, a dependência HTTP e a política de particionamento; não devem ser presumidas no código.

## 8. Referências do repositório

- `doc.api.md`: base URL, endpoints, filtros, identificadores, datas e limitações da OpenF1.
- `SKILL.md`: padrões obrigatórios de Python/Poetry, arquitetura `src/`, Ruff, pytest, MkDocs, idempotência, contratos, segurança e observabilidade.
