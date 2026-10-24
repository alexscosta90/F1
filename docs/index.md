# F1 OpenF1 Data Pipeline

Projeto local de engenharia de dados para consultar, validar, transformar e persistir sessões históricas de F1.

## Escopo do MVP

A execução consulta `/meetings` e `/sessions` por temporada e coleta, por sessão, os endpoints `drivers`, `laps`, `session_result`, `starting_grid` e `stints`. Outros endpoints podem ser selecionados pelo CLI.

## Limites da fonte

Dados históricos gratuitos começam em 2023; dados em tempo real exigem assinatura. Disponibilidade, atraso e campos variam por endpoint e sessão. A API pode retornar listas vazias. Falhas HTTP, rede e JSON inválido encerram a execução.

`/starting_grid` usa `session_key` de uma sessão `Qualifying` ou `Sprint Qualifying`. O coletor pula essa chamada para outros tipos de sessão e informa o motivo no manifesto.

## Navegação

- [Início rápido](getting-started.md)
- [Arquitetura e contratos](architecture.md)
- [Dashboard local](dashboard.md)
- [Desenvolvimento e testes](development.md)
