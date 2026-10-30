# 🏎️ F1 Analytics | Pipeline de Dados e Dashboard

**Análise de dados da Fórmula 1 com Python, OpenF1 e Streamlit.**

Projeto prático de Engenharia de Dados desenvolvido durante meus estudos, utilizando dados históricos da Fórmula 1 disponibilizados pela API OpenF1.

A proposta foi construir um pipeline capaz de coletar, organizar e disponibilizar informações de corridas, pilotos, equipes, voltas e resultados, reunindo esses dados em um dashboard interativo.

O projeto coloca em prática conceitos de consumo de APIs, processamento de dados, automação, testes e visualização.

### 🏁 Acesse o dashboard

**[🚀 Explorar F1 Analytics](https://f1alex.streamlit.app/)**

O dashboard permite explorar diferentes temporadas e sessões, comparar pilotos e equipes e analisar dados de desempenho nas pistas.

## 🛠️ Tecnologias utilizadas

| Tecnologia | Aplicação |
|---|---|
| Python | Desenvolvimento do pipeline |
| OpenF1 API | Fonte de dados da Fórmula 1 |
| Pandas | Manipulação e análise de dados |
| Streamlit | Dashboard interativo |
| Plotly | Gráficos e visualizações |
| Poetry | Ambiente virtual e dependências |
| Pytest / pytest-cov | Testes automatizados e cobertura |
| Ruff | Lint e formatação de código |
| MkDocs Material | Documentação técnica |
| Git / GitHub | Versionamento e organização |

## 🏗️ Arquitetura do projeto

O pipeline consulta a API OpenF1, identifica as etapas e sessões disponíveis e realiza a coleta dos dados.

```text
       OPENF1 API
            |
            v
   COLETA DE DADOS
        Python
            |
            v
   VALIDAÇÃO E CONTROLE
      Logs / Manifestos
            |
            v
     ARMAZENAMENTO
      Arquivos JSONL
            |
            v
     PROCESSAMENTO
     Python / Pandas
            |
            v
      F1 ANALYTICS
   Streamlit + Plotly
```

Os dados coletados são armazenados por temporada, sessão e endpoint, facilitando a organização e o reprocessamento.

O projeto também possui mecanismos de controle de requisições, novas tentativas após falhas e registros das execuções.

## 📊 Funcionalidades do dashboard

O F1 Analytics possui seis páginas principais:

| Página | O que é possível analisar |
|---|---|
| 🏁 Dashboard executivo | Visão geral dos indicadores da temporada ou sessão |
| 🏎️ Corridas | Informações sobre Grandes Prêmios e sessões |
| 👨‍🚀 Pilotos | Consulta e comparação de pilotos |
| 🏆 Equipes | Análise das equipes e classificações disponíveis |
| ⏱️ Voltas | Tempos de volta, desempenho e estratégias |
| 📋 Resultados | Classificações e resultados oficiais |

### Filtros interativos

É possível selecionar temporada, Grande Prêmio, tipo de sessão, equipe e piloto, conforme a disponibilidade dos dados.

O dashboard também apresenta indicadores como melhor volta, velocidade máxima e informações de classificação.

## 🌐 Modos Online e Offline

O dashboard trabalha com duas fontes de dados:

**Online:** consulta a API OpenF1, com controle de requisições, novas tentativas e cache temporário.

**Offline:** utiliza arquivos JSONL armazenados localmente, permitindo consultar dados previamente coletados sem realizar novas chamadas à API.

Se a consulta online falhar, a aplicação pode utilizar os dados locais disponíveis.

Essa separação permite explorar o projeto mesmo quando a API apresenta limitações ou indisponibilidade, desde que os dados necessários já tenham sido coletados.

## 📁 Estrutura do repositório

```text
F1/
├── .github/             # Configurações do GitHub
├── .streamlit/          # Configurações do dashboard
├── data/                # Dados locais organizados por sessão
├── docs/                # Documentação técnica
├── src/
│   └── f1/             # Código da aplicação
├── tests/               # Testes automatizados
├── Dockerfile           # Containerização
├── mkdocs.yml           # Configuração da documentação
├── poetry.lock          # Dependências resolvidas
├── pyproject.toml       # Configuração do projeto
└── README.md
```

## ▶️ Como executar o projeto

### Pré-requisitos

- Python 3.12
- Poetry 2.x
- Git

### 1. Clone o repositório

```bash
git clone https://github.com/alexscosta90/F1.git
cd F1
```

### 2. Instale as dependências

```bash
poetry install
```

### 3. Execute a coleta

Exemplo para a temporada de 2024:

```bash
poetry run f1 --year 2024
```

Também é possível selecionar sessões e endpoints específicos:

```bash
poetry run f1 --year 2024 --session-key 9159 --endpoints laps,stints
```

As respostas são armazenadas em arquivos JSONL, organizados por temporada e sessão.

### 4. Inicie o dashboard

```bash
poetry run dashboard
```

O Streamlit abrirá a aplicação localmente no navegador.

**Observação:** o modo Online depende da disponibilidade da API. Dados históricos podem ser consultados sem credenciais, enquanto o acesso em tempo real está sujeito às condições de autenticação e assinatura da OpenF1.

## 🧪 Qualidade de código e testes

O projeto utiliza ferramentas de qualidade para manter a organização do código e verificar seu comportamento.

**Lint:**

```bash
poetry run ruff check .
```

**Formatação:**

```bash
poetry run ruff format . --check
```

**Testes e cobertura:**

```bash
poetry run pytest tests/unit --cov=f1 --cov-report=term-missing --cov-fail-under=50
```

**Documentação:**

```bash
poetry run mkdocs build
```

A configuração atual estabelece uma cobertura mínima de 50% para o escopo medido.

## 📚 Documentação

O repositório possui documentação adicional com informações sobre arquitetura, contratos, desenvolvimento, testes e funcionamento do dashboard.

- [Documentação técnica](docs/index.md)
- [Guia do dashboard e deploy](docs/dashboard.md)

## 📡 Fonte dos dados

Os dados são obtidos por meio da [OpenF1 API](https://openf1.org/), que disponibiliza informações relacionadas à Fórmula 1, incluindo pilotos, sessões, voltas, resultados e outros dados de desempenho.

A disponibilidade das informações depende da temporada, do tipo de sessão e das condições de acesso à API.

Este é um projeto pessoal de estudo e análise de dados, sem vínculo oficial com a Fórmula 1 ou suas equipes.

## 🎯 Sobre o projeto

Desenvolvi este projeto como parte da minha jornada de aprendizagem em Engenharia de Dados e Inteligência Artificial.

Além do interesse pela Fórmula 1, a proposta foi aplicar conhecimentos técnicos em um cenário prático, trabalhando com consumo de APIs, organização de dados, automação, testes e desenvolvimento de dashboards.

O projeto segue em evolução, com oportunidades de aprimoramento nas análises, visualizações e funcionalidades.

---

### 👨‍💻 Autor

**Alex Santos da Costa**

Engenheiro Eletricista | Pós-graduando em Engenharia de Dados e Inteligência Artificial

[GitHub](https://github.com/alexscosta90) | [LinkedIn](https://www.linkedin.com/in/alexsantosdacosta/) | [Dashboard F1](https://f1alex.streamlit.app/)
