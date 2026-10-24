# OpenF1 API — resumo

Referência resumida da [documentação oficial](https://openf1.org/docs/), consultada em 22/10/2026.

## Visão geral

- API HTTP que fornece dados de Fórmula 1 em JSON e CSV.
- Base URL: `https://api.openf1.org/v1/`.
- Dados históricos (a partir de 2023) são gratuitos e não exigem autenticação. Dados em tempo real exigem assinatura paga.
- A API é um projeto independente e não é afiliada à Fórmula 1.
- As respostas JSON normalmente são listas de objetos; campos comuns incluem `meeting_key`, `session_key`, `driver_number` e `date`.
- Use `latest` como valor de `meeting_key` ou `session_key` para consultar a reunião ou sessão atual/mais recente.

## Endpoints principais

| Endpoint | Conteúdo |
| --- | --- |
| `/car_data` | Telemetria do carro: velocidade, marcha, RPM, acelerador, freio e estado do DRS (aprox. 3,7 amostras/s). |
| `/championship_drivers` *(beta)* | Pontos e posições do campeonato de pilotos; disponível apenas para sessões de corrida. |
| `/championship_teams` *(beta)* | Pontos e posições do campeonato de equipes; disponível apenas para sessões de corrida. |
| `/drivers` | Dados dos pilotos numa sessão: nome, número, acrônimo, equipe, cor e foto. |
| `/intervals` | Intervalo para o carro à frente e diferença para o líder; corridas, atualização aproximada a cada 4 s. |
| `/laps` | Tempos de volta e setores, velocidades em pontos de medição, volta de saída dos boxes e mini-setores. Mini-setores não estão disponíveis durante corridas. |
| `/location` | Coordenadas aproximadas `x`, `y`, `z` dos carros (aprox. 3,7 amostras/s); não informa posição lateral e a origem é arbitrária. |
| `/meetings` | Etapas/fins de semana: circuito, país, local, datas, ano e identificadores. |
| `/overtakes` | Trocas de posição, incluindo ultrapassagens em pista e alterações por pit stop ou penalidade; apenas corridas e pode estar incompleto. |
| `/pit` | Eventos de entrada/saída e duração de paradas nos boxes. |
| `/position` | Posição dos pilotos ao longo da sessão. |
| `/race_control` | Mensagens de controle de corrida, como bandeiras, incidentes e avisos. |
| `/sessions` | Sessões de uma etapa, com tipo, nome, datas e identificadores. |
| `/session_result` | Classificação/resultado da sessão; pode aparecer alguns minutos após a publicação oficial. |
| `/starting_grid` | Grid de largada; disponível alguns minutos após a publicação oficial. |
| `/stints` | Stints e pneus: composto, voltas inicial/final e idade do pneu no início. |
| `/team_radio` | Gravações de rádio disponíveis. A seleção é limitada; a partir de 2026 muitas sessões não têm dados de rádio. |
| `/weather` | Clima no circuito: temperaturas, umidade, pressão, chuva e vento; atualização aproximada a cada minuto. |

## Consultas e filtros

`/starting_grid` é consultado com `session_key` de uma sessão `Qualifying` ou `Sprint Qualifying`. Apesar de ser um endpoint válido, ele não se aplica a sessões de treino ou corrida; filtre o tipo da sessão antes de chamá-lo.

Filtros são parâmetros da URL e podem ser aplicados a qualquer atributo, exceto campos de array. Filtros diferentes combinam-se na mesma consulta. Operadores aceitos:

- Igualdade: `?session_key=9161&driver_number=1`
- Comparações: `?lap_duration>=90`, `?position<=3`, `?speed>300`
- Datas/intervalos: `?date>=2023-09-16T13:00:00Z&date<2023-09-16T14:00:00Z`
- Para passar operadores em clientes HTTP, codifique-os na URL quando necessário (por exemplo, `<` como `%3C`).

Datas são retornadas em UTC e ISO 8601. A documentação aceita vários formatos de data, mas recomenda-se usar ISO 8601, com fuso explícito.

## Exemplos

```http
GET https://api.openf1.org/v1/sessions?year=2026&country_name=Singapore
GET https://api.openf1.org/v1/drivers?session_key=latest
GET https://api.openf1.org/v1/laps?session_key=9161&driver_number=63&lap_number=8
GET https://api.openf1.org/v1/car_data?session_key=9159&driver_number=55&speed%3E=315
```

Uma chamada simples em JavaScript:

```js
const response = await fetch(
  "https://api.openf1.org/v1/drivers?session_key=latest",
);
const drivers = await response.json();
```

## Identificadores e considerações

- `meeting_key` identifica uma etapa; `session_key` identifica uma sessão. Consulte `/meetings` e `/sessions` para descobrir esses valores.
- `driver_number` identifica o piloto na temporada.
- A disponibilidade e a frequência variam por endpoint; dados em tempo real, rádio, ultrapassagens e campeonatos têm limitações específicas descritas acima.
- Dados e campos podem conter valores nulos ou estar ausentes conforme a sessão e a disponibilidade da fonte.

