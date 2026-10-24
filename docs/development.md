# Desenvolvimento e testes

O pacote vive em `src/f1/`; Poetry controla ambiente e dependências. A versão mínima local é Python 3.12, definida em `.python-version` e `pyproject.toml`.

## Comandos

```powershell
poetry install
poetry run ruff check .
poetry run ruff format .
poetry run ruff format . --check
poetry run ruff check . --select I
poetry run pytest tests/unit --cov=f1 --cov-report=term-missing --cov-fail-under=50
poetry run pytest
poetry run mkdocs serve
poetry run mkdocs build
```

Os testes unitários usam mocks e fixtures locais, sem depender da API. Não há credenciais de API histórica. `.env` é ignorado e `.env.example` não contém segredos.

## Operação

O CLI valida ano e endpoints, aceita timeout e retries, descobre identificadores na API e emite início/fim, contagens e duração. O padrão é timeout de 30 segundos por chamada e até 3 retries (4 tentativas no total). Para falhas de rede e respostas transitórias sem `Retry-After`, os intervalos são 0,5, 1 e 2 segundos, com jitter de até 20% (limitado a 1 segundo). Quando a resposta traz `Retry-After` numérico, o cliente respeita esse tempo e adiciona o mesmo jitter. Cada falha registra endpoint, URL, status, até 4 KiB do corpo de erro, tipo/mensagem da exceção e stack trace; falhas de rede registram status/corpo como ausentes.

A OpenF1 publica limite gratuito de 3 requisições por segundo e 30 por minuto. O cliente limita globalmente o processo a 28 requisições em qualquer janela móvel de 60 segundos e espaça as chamadas por pelo menos `60/28` segundos. As tentativas de retry também contam. A margem de duas chamadas reduz o risco de consumo concorrente do mesmo limite por outros processos. Uma configuração operacional mais conservadora para a rede é `--timeout 20 --retries 2`; a limitação de taxa continua ativa. Respostas com `Retry-After` elevam o bloqueio global pelo tempo indicado, inclusive retries posteriores de outros endpoints. A documentação pública consultada não especifica um timeout máximo imposto pelo servidor.

O volume planejado de uma coleta é `2 + Σ endpoints elegíveis por sessão`: duas chamadas de descoberta (`meetings` e `sessions`) mais uma por endpoint e sessão. No conjunto padrão, cada sessão não qualificatória usa quatro endpoints; uma sessão `Qualifying` ou `Sprint Qualifying` usa cinco. Por exemplo, 120 sessões com 24 sessões de qualificação requerem cerca de 506 chamadas sem retries (`2 + 4×120 + 24`). O limitador as distribui por cerca de 18 minutos a 28 chamadas/minuto; cada retry ocupa outro slot.

Reprocessamento/backfill é feito informando o mesmo ano/sessão novamente.

O teste de interface usa `streamlit.testing.v1.AppTest` para executar os modos Online e Offline sem navegador. O entrypoint visual `dashboard.py` é omitido do relatório do Coverage porque o runner do Streamlit avalia páginas isoladamente; os repositórios, serviços, leitor JSONL e cliente continuam sujeitos à cobertura mínima de 50%.
