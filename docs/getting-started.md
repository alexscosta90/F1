# Início rápido

Requer Python 3.12 e Poetry 2.x.

```powershell
poetry config virtualenvs.in-project true --local
poetry install
poetry run f1 --year 2024
```

Escolha `--meeting-key`, `--session-key`, `--endpoints` e `--output-dir` conforme necessário. Por padrão, o processo grava JSONL em `data/<ano>/<session_key>/` e não precisa de arquivo `.env` nem credenciais.

```powershell
poetry run f1 --year 2024 --session-key 9159 --endpoints drivers,laps,stints
```

Use somente anos e sessões para os quais a API disponibilize dados. O valor `--year` é obrigatório e não há temporada codificada no pipeline.

Para abrir o dashboard, execute `poetry run dashboard`. Ele usa Online por padrão; escolha Offline na barra lateral para ler apenas os arquivos locais. Veja [Dashboard F1 Analytics](dashboard.md).
