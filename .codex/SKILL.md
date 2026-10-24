---
name: python-data-engineering
description: Regras obrigatórias para implementar, revisar e manter projetos Python de Engenharia de Dados com Poetry, arquitetura src, Ruff, pytest e MkDocs Material.
---

# Engenharia de Dados com Python

Este documento define o padrão obrigatório para projetos Python do time de Engenharia de Dados. Aplique-o ao criar, implementar, refatorar, revisar e manter código. As regras de um repositório podem especializar este padrão, desde que não reduzam seus requisitos sem uma decisão técnica registrada.

Use `<pacote>` como marcador para o nome importável real do projeto (por exemplo, `f1`). Use `projeto` somente nos exemplos genéricos. Antes de alterar um projeto existente, leia `pyproject.toml`, a documentação e a estrutura existente; adapte os exemplos sem renomear componentes sem necessidade.

## 1. Princípios obrigatórios

- Escreva código modular, legível, reutilizável e fácil de manter, com alta coesão e baixo acoplamento.
- Prefira a solução mais simples que cumpra os requisitos. Evite duplicação, funções extensas, camadas artificiais e abstrações sem benefício concreto.
- Separe regras de negócio de I/O, infraestrutura, configuração e orquestração.
- Use type hints em parâmetros, retornos e estruturas relevantes. Não esconda tipos desconhecidos com `Any` sem motivo documentado.
- Escreva docstrings em módulos, classes e funções públicas. Use um padrão consistente (Google style) e explique propósito, argumentos, retorno e exceções relevantes; não repita literalmente a assinatura.
- Trate erros explicitamente. Capture exceções específicas, preserve a causa com `raise ... from exc` quando traduzir erros e não silencie falhas.
- Use `logging` para eventos operacionais; não use `print()` no código de produção.
- Mantenha configuração e credenciais fora do código. Nunca adicione tokens, senhas, chaves privadas ou credenciais reais ao repositório, exemplos, logs ou testes.
- Projete execução local, automação, testes e CI como usos de primeira classe. Comandos devem funcionar a partir da raiz do projeto.

## 2. Python, Poetry e dependências

Poetry é a única ferramenta para criar e gerenciar o ambiente virtual, dependências e empacotamento. Não use `pip install`, `pip uninstall` ou `pip` para instalar, remover ou gerenciar dependências, nem recomende instalação manual na venv. Instale ferramentas e execute comandos por `poetry`/`poetry run`.

### Regras

1. Declare todas as dependências de runtime e desenvolvimento no `pyproject.toml`; mantenha `poetry.lock` versionado em aplicações e projetos executáveis.
2. Nunca edite `poetry.lock` manualmente. Altere dependências com `poetry add`/`poetry remove` e revise o lockfile resultante.
3. Fixe/documente a faixa compatível do Python em `pyproject.toml` e a versão local acordada em `.python-version`. Use `pyenv` para instalar e selecionar essa versão quando necessário.
4. Configure a venv local do Poetry em `.venv`. Não ative nem modifique a venv por fora do Poetry.
5. Separe dependências de desenvolvimento, teste e documentação em grupos; não adicione pacote sem necessidade demonstrável. Ao escolher uma dependência, prefira a biblioteca padrão se ela for suficiente.
6. Confira a sintaxe contra a versão de Poetry declarada/adotada pelo repositório. Os exemplos abaixo usam Poetry 2.x; não misture sintaxe de versões sem explicar a compatibilidade.

### Configuração e comandos (Poetry 2.x)

```bash
# Instalar/selecionar a versão documentada do Python
pyenv install <versao>
pyenv local <versao>

# Guardar a configuração no repositório
poetry config virtualenvs.in-project true --local

# Instalar ou sincronizar dependências do projeto
poetry install
poetry env info
poetry run python --version

# Gerenciar dependências
poetry add <pacote>
poetry add --group dev <pacote>
poetry add --group test <pacote>
poetry add --group docs <pacote>
poetry remove <pacote>

# Validar metadados e lockfile
poetry check
```

Não inclua uma versão fictícia nos arquivos do projeto: escolha a versão suportada e mantenha `.python-version`, `requires-python` e configuração das ferramentas consistentes.

## 3. Arquitetura e organização

Adote o layout `src/`: código de produção reside exclusivamente no pacote dentro de `src/`. A árvore abaixo é uma referência, não uma ordem para criar diretórios vazios. Adapte nomes e camadas ao domínio e ao tamanho do projeto.

```text
projeto/
├── .github/workflows/
├── docs/
├── tests/
│   ├── unit/
│   └── integration/
├── src/<pacote>/
│   ├── __init__.py
│   ├── config.py
│   ├── ingestion/
│   ├── transformations/
│   ├── validation/
│   ├── storage/
│   ├── services/
│   └── logging_config.py
├── .env.example
├── .gitignore
├── .python-version
├── mkdocs.yml
├── pyproject.toml
├── poetry.lock
└── README.md
```

### Limites e decisões de módulos

- Separe ingestão, transformação, validação, persistência e orquestração conforme as responsabilidades reais. Um módulo deve ter um motivo claro para mudar.
- Mantenha regras de negócio independentes de clientes HTTP, bancos, clouds e filesystem. Isole essas integrações em módulos de infraestrutura e injete dependências nas funções/serviços que as utilizam.
- Evite módulos monolíticos, dependências circulares, estado global mutável e I/O ou criação de recursos como efeito colateral de importação.
- Não use `utils.py` como depósito genérico. Coloque funções perto do conceito que implementam; extraia um módulo compartilhado apenas quando houver coesão e mais de um consumidor real.
- Crie um módulo quando houver uma responsabilidade coesa, uma fronteira de dependência útil ou tamanho que dificulte localizar e testar o comportamento. Reutilize um módulo existente quando a função pertença ao mesmo conceito e não torne sua responsabilidade ambígua.
- Uma abstração é desnecessária quando só renomeia uma chamada, tem um único caminho sem variação real ou adiciona indireção sem permitir teste, substituição ou clareza. Prefira funções simples até que uma necessidade concreta justifique interface ou classe.
- As transformações e validações centrais devem poder ser testadas sem acesso a serviços externos.

## 4. Ruff: lint, formato e imports

Ruff é obrigatório para lint, formatação e ordenação de imports. Não introduza Black, isort ou Flake8 sem decisão técnica registrada. Configure no `pyproject.toml` com alvo compatível com o Python do projeto. Habilite pelo menos `E`, `F`, `I`, `B` e `UP`; considere `C4`, `SIM` e regras de complexidade (`C90`) quando adequadas. Corrija alertas genuínos em vez de desativar regras globalmente.

Configuração de referência para Ruff atual (ajuste `target-version` à versão mínima real):

```toml
[tool.ruff]
line-length = 88
target-version = "py312"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "C4", "SIM"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

Comandos obrigatórios, na raiz:

```bash
poetry run ruff check .
poetry run ruff check . --fix
poetry run ruff format .
poetry run ruff format . --check
poetry run ruff check . --select I
```

Antes de concluir uma alteração, execute lint e verificação de formato; formate antes de abrir PR. Revise toda correção automática. Não ignore erro sem justificativa. Se uma supressão local for indispensável, limite-a à linha/regra necessária e explique o motivo em comentário. Não use exclusões globais para mascarar defeitos.

## 5. Testes com pytest e cobertura

Use `pytest` como padrão e `pytest-cov` para medir o pacote de produção (`src/<pacote>/`). A cobertura mínima de testes unitários é **50%**. Linhas cobertas não provam qualidade: valide resultados, invariantes e efeitos observáveis, incluindo cenários de sucesso, erro, limites e entradas inválidas.

### Regras

- Teste regras de negócio, transformações, validações, cálculos e tratamento de erros com dados pequenos, determinísticos e reproduzíveis.
- Isole APIs, bancos e serviços externos em testes unitários com fixtures/mocks apropriados. Testes unitários não usam serviços reais nem credenciais externas.
- Separe testes de integração em `tests/integration/`; identifique claramente seus requisitos externos e não os confunda com a suíte unitária padrão.
- Use nomes descritivos e teste comportamento esperado, não detalhes acidentais da implementação.
- Não reduza o limite de cobertura nem exclua módulos relevantes para fazer CI passar. Exclua somente código comprovadamente fora do escopo executável, com justificativa revisável.
- Execute os testes em ambiente limpo com Poetry.

Configuração de referência:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.coverage.run]
branch = true
source = ["<pacote>"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
show_missing = true
fail_under = 50
```

Substitua `<pacote>` pelo nome importável real (por exemplo, `f1`). Não omita `__init__.py` automaticamente se ele contiver código relevante; nesse caso, inclua-o na medição. Configure `pytest-cov` como dependência de teste.

```bash
poetry run pytest tests/unit
poetry run pytest tests/unit --cov=<pacote> --cov-report=term-missing --cov-fail-under=50
poetry run pytest
```

## 6. Documentação com MkDocs Material

Use `mkdocs-material` para documentação técnica versionada no repositório. Declare MkDocs e o tema no grupo `docs` do Poetry. Mantenha a documentação atualizada junto às mudanças de funcionalidade e arquitetura.

Estrutura sugerida (crie apenas páginas necessárias):

```text
docs/
├── index.md
├── getting-started.md
├── architecture.md
├── development.md
├── testing.md
└── modules/
```

O `README.md` deve explicar objetivo, requisitos, instalação, configuração e execução. Documente módulos principais, fluxo de dados, configuração de pyenv/Poetry, lint, formatação, testes, variáveis de ambiente, decisões técnicas e limitações conhecidas. `.env.example` contém somente nomes e valores fictícios ou vazios. Mantenha exemplos executáveis compatíveis com o código atual; use diagramas quando tornarem um pipeline ou dependências mais claros. Evite duplicação e páginas sem utilidade prática.

Comandos obrigatórios:

```bash
poetry install
poetry run mkdocs serve
poetry run mkdocs build
```

`mkdocs build` deve terminar sem erros antes da entrega/PR. O `mkdocs.yml` deve declarar explicitamente `docs_dir` e navegação coerentes com os arquivos existentes.

## 7. Práticas de Engenharia de Dados

### 7.1 Fluxo e idempotência

- Separe leitura/ingestão, transformação, validação e gravação. Faça funções de transformação receberem dados e parâmetros explícitos e retornarem resultado sem executar I/O oculto.
- Torne uma execução repetível sem duplicar nem corromper dados quando o destino e o cenário permitirem. Defina a chave de idempotência, a unidade de reprocessamento e a política de escrita (por exemplo, upsert por chave natural, substituição atômica de partição ou deduplicação determinística).
- Use checkpoints/watermarks persistidos somente após a gravação confirmada. Defina como reprocessar janelas atrasadas e como recuperar falha parcial. Não avance o watermark se a escrita falhar.
- Especifique comportamento para reexecução, dados duplicados e execução concorrente; não presuma que um job será executado uma única vez.

### 7.2 Contratos, qualidade e evolução de schema

- Defina o contrato de entrada e saída: campos, tipos, nulabilidade, chaves, granularidade, timezone, unidades e regras de qualidade.
- Valide dados na fronteira de entrada e antes de publicar/gravar resultados. Falhe com erro acionável para violações críticas; contabilize e encaminhe registros rejeitados conforme política documentada, sem descartá-los silenciosamente.
- Trate campos ausentes, extras, nulos e mudanças de tipo de forma explícita. Registre compatibilidade/evolução de schema e preserve rastreabilidade entre versão do contrato e execução.
- Use amostras representativas para desenvolvimento; não carregue conjuntos inteiros em memória sem avaliar volume e limites.

### 7.3 APIs, arquivos, SQL e armazenamento

- Para APIs, defina timeout, paginação, limites de taxa, retries limitados com backoff e jitter para falhas transitórias, e comportamento para erros permanentes. Não repita indefinidamente operações não idempotentes; use chave de idempotência quando suportada.
- Para arquivos, valide formato, codificação, compressão, tamanho e convenção de nomes. Grave saídas de forma atômica quando possível e não substitua um resultado válido por saída parcial.
- Use parâmetros vinculados em consultas SQL; nunca concatene entrada não confiável na query. Mantenha consultas e transações explícitas e limite o escopo da transação.
- Escolha formatos e particionamento segundo leitores, volume e padrão de consulta. Evite arquivos minúsculos, partições de alta cardinalidade e leitura/escrita desnecessária de colunas.
- Libere conexões, cursores, sessões e handles com context managers ou mecanismos equivalentes. Defina limites de pool e fechamento no ciclo de vida da aplicação.

### 7.4 Resiliência e processamento distribuído

- Diferencie falhas transitórias de permanentes. Limite retries e tempo total; registre tentativas e erro final. Não esconda falhas transformando-as em sucesso vazio.
- Projete tarefas para reprocessamento de partições/lotes e torne efeitos externos seguros para repetição quando possível.
- Em processamento distribuído, evite ações que movam dados ao driver sem necessidade, operações não determinísticas e compartilhamento de estado mutável. Use particionamento e paralelismo medidos, respeitando limites de memória, shuffle e concorrência do destino.
- Não assuma garantias de “exactly once” sem verificar as garantias do orquestrador, origem e destino. Documente a semântica efetiva (at-least-once/at-most-once) e a estratégia de deduplicação/commit.

### 7.5 Observabilidade, segurança e operação

- Registre início/fim, identificador de execução, intervalo/partição processada, contagens lidas/aceitas/rejeitadas/gravadas, duração e falhas. Use logs estruturados quando suportados.
- Inclua contexto suficiente para diagnosticar uma execução, sem registrar conteúdo sensível, dados pessoais desnecessários, segredos ou payloads completos.
- Use métricas para volume, latência, erros e atrasos de atualização quando houver infraestrutura para isso. Defina alertas com limites e responsáveis operacionais no projeto.
- Leia segredos de variáveis de ambiente ou mecanismo de secret manager da plataforma. Valide configurações obrigatórias na inicialização e apresente nomes de variáveis ausentes sem revelar valores.
- Documente execução, parâmetros, dependências externas, backfill, reprocessamento e procedimento de recuperação.

## 8. Configuração e segurança

- Versione `.env.example` com nomes, explicação e valores de exemplo não sensíveis; inclua `.env` e credenciais locais no `.gitignore`.
- Valide configuração na inicialização e falhe cedo com mensagem clara. Não mantenha valores secretos como defaults.
- Não registre tokens, strings de conexão, dados pessoais ou registros brutos sensíveis. Remova ou mascare campos sensíveis antes do log.
- Não use `print()` para contornar logging nem credenciais reais em fixtures, notebooks, snapshots ou documentação.

## 9. Checklist verificável para alterações e revisão

Antes de concluir uma tarefa ou aprovar um PR, confirme os itens aplicáveis:

- [ ] Código de produção está em `src/<pacote>/`; módulos têm responsabilidade clara e não introduzem ciclos ou efeitos colaterais em imports.
- [ ] Type hints, docstrings públicas e tratamento explícito de erros estão presentes onde necessários.
- [ ] Dependências foram justificadas e gerenciadas pelo Poetry; `poetry.lock` não foi editado manualmente.
- [ ] Ruff lint, formato e imports passam; supressões locais estão justificadas.
- [ ] Testes cobrem comportamento, erros e limites relevantes; suíte unitária alcança pelo menos 50% sem exclusões artificiais.
- [ ] Testes não dependem de APIs/bancos reais nem de credenciais externas.
- [ ] `poetry run mkdocs build` passa e a documentação reflete a alteração.
- [ ] Segredos não estão em código, fixtures, documentação, logs ou arquivos versionados.
- [ ] Para pipeline: contrato, idempotência/reprocessamento, falhas, contagens e observabilidade estão definidos conforme aplicável.
- [ ] `README.md`, `.env.example` e configuração de ambiente permanecem coerentes com o comportamento atual.

Execute os validadores pertinentes antes de declarar o trabalho pronto e informe quais comandos passaram e quaisquer limitações reais encontradas.
