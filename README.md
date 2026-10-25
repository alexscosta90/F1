# F1 OpenF1 Data Pipeline

Pipeline local em Python para descobrir etapas e sessões da Fórmula 1 e coletar resultados, pilotos, voltas, grid e stints da API histórica OpenF1.

## Requisitos

- Python 3.12 (faixa suportada: `>=3.12,<3.13`)
- Poetry 2.x

## Instalação

```powershell
poetry config virtualenvs.in-project true --local
poetry install
```

## Execução

Coleta todos os endpoints padrão de todas as sessões disponíveis para uma temporada:

```powershell
poetry run f1 --year 2024
```

Filtre etapa ou sessão e selecione endpoints/destino:

```powershell
poetry run f1 --year 2024 --meeting-key 1234 --endpoints drivers,laps,weather --output-dir data
poetry run f1 --year 2024 --session-key 9159 --endpoints laps,stints
```

A API é consultada sem credenciais. O programa descobre `meeting_key` e `session_key`, grava logs operacionais e escreve em `data/<ano>/<session_key>/<endpoint>.jsonl`. Cada reexecução substitui atomicamente os arquivos do endpoint. Um `manifest.jsonl` por sessão registra escopo, contagens, duração e identificador da execução.

## Decisão de armazenamento do MVP

O plano ainda não informa o produto analítico nem o padrão de consulta. Para tornar o MVP local executável, JSONL em diretórios locais foi escolhido provisoriamente por não exigir serviço ou credenciais. O limite de reprocessamento é uma sessão; arquivos são substituídos por endpoint, com deduplicação natural pelo snapshot completo retornado pela fonte. A gravação é atômica por arquivo. Uma falha durante publicação de vários endpoints pode deixar endpoints de execuções diferentes, então consulte o manifesto e reexecute a sessão. O destino deverá ser reavaliado quando volume, leitores e análise prioritária forem definidos.

## Desenvolvimento e qualidade

```powershell
poetry run ruff check .
poetry run ruff format . --check
poetry run ruff check . --select I
poetry run pytest tests/unit --cov=f1 --cov-report=term-missing --cov-fail-under=50
poetry run mkdocs build
```

Veja [a documentação técnica](docs/index.md) para arquitetura, contratos e desenvolvimento.

## Limitações

Dados históricos gratuitos estão disponíveis a partir de 2023. Dados em tempo real requerem assinatura. Disponibilidade e atraso variam por endpoint e sessão; respostas vazias são válidas, mas falhas HTTP ou de rede não são convertidas em sucesso vazio. Campos ausentes, extras e nulos são preservados; registros incompatíveis com a sessão são contabilizados como rejeitados. Veja `.codex/doc.api.md` para o resumo de endpoints utilizado no projeto.

## Dashboard F1 Analytics

O dashboard abre por padrão no modo **Online** e usa o cliente OpenF1 existente, com o rate limiter global e os retries atuais. As respostas ficam em cache por um minuto e a interface atualiza automaticamente. Se uma consulta falhar, a fonte muda para **Offline** e lê os JSONL locais; Offline não faz chamadas externas.

```powershell
poetry install
poetry run dashboard
```

As seis páginas são Dashboard executivo, Corridas, Pilotos, Equipes, Voltas e Resultados. Os filtros incluem ano, Grande Prêmio, tipo de sessão, equipe e piloto. O catálogo online é salvo localmente para manter os nomes oficiais no modo Offline. Veja o [guia do dashboard e deploy](docs/dashboard.md).

