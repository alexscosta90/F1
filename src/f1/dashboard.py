"""F1 analytics dashboard with online and local JSONL sources."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import plotly.express as px
import streamlit as st
from pandas.io.formats.style import Styler

from f1.config import Settings
from f1.dashboard_analytics import (
    best_lap_comparison,
    best_laps,
    classification_table,
    filter_driver_rows,
    ordered_results,
    position_history,
    positive_numeric_values,
    stint_timeline,
    valid_laps,
)
from f1.dashboard_data import available_years, load_season, snapshot_years
from f1.dashboard_repository import FileRepository, OpenF1Repository
from f1.dashboard_service import DashboardService
from f1.dashboard_theme import (
    BACKGROUND,
    BORDER,
    CHART_COLORS,
    GRID,
    MUTED_TEXT,
    SURFACE,
    TEAM_COLORS,
    TEXT,
)
from f1.ingestion.client import OpenF1Client, OpenF1Error

st.set_page_config(
    page_title="F1 | Race intelligence", page_icon=":material/speed:", layout="wide"
)

PAGES = [
    "Dashboard executivo",
    "Corridas",
    "Pilotos",
    "Equipes",
    "Voltas",
    "Resultados",
]
ENDPOINTS_BY_PAGE = {
    "Dashboard executivo": (
        "drivers",
        "laps",
        "session_result",
        "championship_drivers",
        "championship_teams",
    ),
    "Corridas": ("drivers", "laps", "session_result", "position"),
    "Pilotos": ("drivers", "laps", "session_result"),
    "Equipes": ("drivers", "laps", "session_result", "championship_teams"),
    "Voltas": ("drivers", "laps", "stints"),
    "Resultados": (
        "drivers",
        "session_result",
        "position",
        "championship_drivers",
        "championship_teams",
    ),
}


@st.cache_data(ttl=3500, max_entries=4, show_spinner=False)
def oauth_access_token(username: str, password: str) -> str:
    """Obtain an OAuth2 token on the server and cache it before expiry."""
    request = Request(
        "https://api.openf1.org/token",
        data=urlencode({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise OpenF1Error("Não foi possível autenticar na OpenF1.") from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise OpenF1Error("A OpenF1 não retornou um token válido.")
    return str(payload["access_token"])


def _access_token() -> str | None:
    try:
        secrets = st.secrets.get("openf1", {})
    except st.errors.StreamlitSecretNotFoundError:
        secrets = {}
    username = secrets.get("username") or os.environ.get("OPENF1_USERNAME")
    password = secrets.get("password") or os.environ.get("OPENF1_PASSWORD")
    token = secrets.get("access_token") or os.environ.get("F1_API_TOKEN")
    return (
        oauth_access_token(str(username), str(password))
        if username and password
        else (str(token) if token else None)
    )


@st.cache_resource(max_entries=4, show_spinner=False)
def _client(token: str | None) -> OpenF1Client:
    return OpenF1Client(Settings(api_token=token))


@st.cache_data(ttl=60, max_entries=8, show_spinner=False)
def _online_catalog(year: int, token: str | None) -> dict[str, list[dict[str, object]]]:
    return DashboardService(OpenF1Repository(_client(token))).catalog(year)


@st.cache_data(ttl=60, max_entries=128, show_spinner=False)
def _online_endpoint(
    year: int, session_key: int, endpoint: str, token: str | None
) -> list[dict[str, object]]:
    service = DashboardService(OpenF1Repository(_client(token)))
    return service.session_data(year, session_key, [endpoint])[endpoint]


@st.cache_data(max_entries=8, show_spinner=False)
def _offline_catalog(
    data_dir: str, year: int, fingerprint: tuple[tuple[str, int], ...]
) -> dict[str, list[dict[str, object]]]:
    del fingerprint
    return FileRepository(Path(data_dir)).load_catalog(year)


@st.cache_data(max_entries=4, show_spinner=False)
def _offline_season(
    data_dir: str, year: int, fingerprint: tuple[tuple[str, int], ...]
) -> dict[str, pd.DataFrame]:
    del fingerprint
    return {
        name: _frame(rows) for name, rows in load_season(Path(data_dir), year).items()
    }


@st.cache_data(max_entries=128, show_spinner=False)
def _offline_endpoint(
    data_dir: str, year: int, session_key: int, endpoint: str, modified_ns: int
) -> list[dict[str, object]]:
    del modified_ns
    return FileRepository(Path(data_dir)).load_endpoint(year, session_key, endpoint)


def _fallback(message: str) -> None:
    if "HTTP 401" in message:
        message = (
            "A OpenF1 recusou o acesso sem autenticacao valida (HTTP 401). "
            "Durante sessoes ao vivo, isso pode afetar tambem dados historicos. "
            "Mudamos para os dados locais disponiveis."
        )
    st.session_state["_force_offline"] = True
    st.session_state["_fallback_message"] = message
    st.rerun()


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _as_int(value: object) -> int | None:
    try:
        return None if pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return None


def _driver_names(drivers: pd.DataFrame) -> dict[int, str]:
    names: dict[int, str] = {}
    for row in drivers.to_dict("records") if "driver_number" in drivers else []:
        number = _as_int(row.get("driver_number"))
        if number is not None:
            name = (
                row.get("full_name")
                or row.get("broadcast_name")
                or row.get("name_acronym")
                or "Driver"
            )
            names[number] = f"{name} (#{number})"
    return names


def _team_names(drivers: pd.DataFrame) -> dict[int, str]:
    return {
        number: str(row.get("team_name") or "Unknown team")
        for row in drivers.to_dict("records")
        if "driver_number" in drivers
        if (number := _as_int(row.get("driver_number"))) is not None
    }


def _team_colors(drivers: pd.DataFrame) -> dict[str, str]:
    colors = {
        key: color
        for name, color in TEAM_COLORS.items()
        for key in (name, name.casefold())
    }
    for row in drivers.to_dict("records") if not drivers.empty else []:
        name, colour = row.get("team_name"), row.get("team_colour")
        known_team = isinstance(name, str) and name.casefold() in {
            team.casefold() for team in TEAM_COLORS
        }
        if isinstance(name, str) and isinstance(colour, str) and not known_team:
            normalized = colour.removeprefix("#")
            if len(normalized) == 6 and all(
                character in "0123456789abcdefABCDEF" for character in normalized
            ):
                colors[name] = f"#{normalized}"
                colors[name.casefold()] = f"#{normalized}"
    return colors


def _styled_team_table(
    frame: pd.DataFrame, drivers: pd.DataFrame
) -> pd.DataFrame | Styler:
    """Add a narrow team-color marker without changing any table values."""
    if "Team" not in frame:
        return frame
    colors = _team_colors(drivers)

    def marker(value: object) -> str:
        color = colors.get(str(value), colors.get(str(value).casefold(), MUTED_TEXT))
        return f"border-left: 3px solid {color}; padding-left: 8px;"

    return frame.style.map(marker, subset=["Team"])


def _classification_column_config() -> dict[str, object]:
    """Configure compact display widths while retaining formatted values."""
    config: dict[str, object] = {
        "Position": st.column_config.NumberColumn(
            "Posição", format="%d", width="small", pinned=True
        ),
        "Pilot": st.column_config.TextColumn("Piloto", width="medium", pinned=True),
        "Team": st.column_config.TextColumn("Equipe", width="small"),
    }
    for column in (
        "Tempo total",
        "Melhor volta",
        "Diferença",
        "Q1",
        "Q2",
        "Q3",
        "Delta Q1",
        "Delta Q2",
        "Delta Q3",
        "Voltas",
        "Situação",
    ):
        config[column] = st.column_config.TextColumn(
            column, width="small", alignment="right"
        )
    return config


def _display_driver(value: object, names: dict[int, str]) -> str:
    number = _as_int(value)
    return (
        names.get(number, "Unknown driver") if number is not None else "Unknown driver"
    )


def _meeting_label(row: pd.Series) -> str:
    name = str(row.get("gp_name") or "Grand Prix")
    country = row.get("country_name")
    return (
        f"{name} · {country}"
        if isinstance(country, str) and country.lower() not in name.lower()
        else name
    )


def _catalog_frames(
    catalog: dict[str, list[dict[str, object]]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meetings, sessions = (
        _frame(catalog.get("meetings", [])),
        _frame(catalog.get("sessions", [])),
    )
    if (
        meetings.empty
        or sessions.empty
        or "meeting_key" not in meetings
        or "meeting_key" not in sessions
    ):
        return meetings, sessions
    meetings = meetings.drop_duplicates("meeting_key").copy()
    for column in ("meeting_name", "meeting_official_name", "location", "country_name"):
        if column not in meetings:
            meetings[column] = None
    meetings["gp_name"] = (
        meetings["meeting_name"]
        .fillna(meetings["meeting_official_name"])
        .fillna(meetings["location"])
        .fillna(meetings["country_name"])
    )
    if meetings["gp_name"].isna().all():
        keys = sorted(meetings["meeting_key"].dropna().unique())
        meetings["gp_name"] = meetings["meeting_key"].map(
            {key: f"Grand Prix {i}" for i, key in enumerate(keys, 1)}
        )
    meetings["gp_label"] = meetings.apply(_meeting_label, axis=1)
    sessions = sessions.drop_duplicates("session_key").merge(
        meetings[["meeting_key", "gp_name", "gp_label"]], on="meeting_key", how="left"
    )
    if "session_type" not in sessions:
        sessions["session_type"] = "Session"
    if "session_name" not in sessions:
        sessions["session_name"] = sessions["session_type"]
    sessions["session_label"] = sessions["session_name"].fillna(
        sessions["session_type"]
    )
    return meetings, sessions


def _context() -> dict[str, object]:
    return st.session_state["_dashboard_context"]


def _plot(fig, alt: str) -> None:
    fig.update_layout(
        template="plotly_dark",
        colorway=CHART_COLORS,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font={"family": "Inter, Segoe UI, sans-serif", "size": 12, "color": TEXT},
        title={"font": {"size": 18, "color": TEXT}, "x": 0, "xanchor": "left"},
        legend={
            "orientation": "h",
            "y": -0.22,
            "x": 0,
            "xanchor": "left",
            "yanchor": "top",
            "font": {"size": 10, "color": MUTED_TEXT},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
        },
        hoverlabel={"bgcolor": SURFACE, "bordercolor": BORDER, "font": {"color": TEXT}},
        autosize=True,
        margin={"l": 20, "r": 20, "t": 58, "b": 66},
    )
    fig.update_xaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        tickfont={"color": MUTED_TEXT, "size": 10},
        title_font={"color": MUTED_TEXT, "size": 11},
        zeroline=False,
    )
    fig.update_yaxes(
        gridcolor=GRID,
        linecolor=BORDER,
        tickfont={"color": MUTED_TEXT, "size": 10},
        title_font={"color": MUTED_TEXT, "size": 11},
        zeroline=False,
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, alt=alt)


def _metrics(items: list[tuple[str, object]]) -> None:
    for start in range(0, len(items), 4):
        columns = st.columns(min(4, len(items) - start))
        for column, (label, value) in zip(
            columns, items[start : start + 4], strict=True
        ):
            column.metric(label, value, border=True)


def _load(endpoints: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    context = _context()
    data: dict[str, pd.DataFrame] = {}
    try:
        for endpoint in endpoints:
            if (
                endpoint.startswith("championship_")
                and context["session_type"] != "Race"
            ):
                data[endpoint] = pd.DataFrame()
                continue
            if context["source"] == "Online":
                rows = _online_endpoint(
                    int(context["year"]),
                    int(context["session_key"]),
                    endpoint,
                    context.get("token"),
                )
            else:
                path = (
                    Path(str(context["data_dir"]))
                    / str(context["year"])
                    / str(context["session_key"])
                    / f"{endpoint}.jsonl"
                )
                rows = _offline_endpoint(
                    str(context["data_dir"]),
                    int(context["year"]),
                    int(context["session_key"]),
                    endpoint,
                    path.stat().st_mtime_ns if path.exists() else 0,
                )
            data[endpoint] = _frame(rows)
    except OpenF1Error as exc:
        if context["source"] == "Online":
            _fallback(
                "A OpenF1 está indisponível. O dashboard mudou para arquivos "
                f"locais. ({exc})"
            )
        raise
    return data


def _selected_data() -> tuple[
    dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    context = _context()
    data = _load(ENDPOINTS_BY_PAGE[str(context["page"])])
    drivers = data.get("drivers", pd.DataFrame())
    names = _team_names(drivers)
    selected = list(context.get("selected_drivers", []))
    team = context.get("team")
    if team != "All teams":
        selected = [number for number, name in names.items() if name == team]
    outputs = []
    for endpoint in ("laps", "session_result", "stints"):
        frame = data.get(endpoint, pd.DataFrame()).copy()
        frame = filter_driver_rows(frame, selected)
        if endpoint == "laps":
            frame = valid_laps(frame)
        elif endpoint == "session_result":
            frame = ordered_results(frame)
        outputs.append(frame)
    return data, *outputs


def _winner(results: pd.DataFrame, names: dict[int, str]) -> str:
    ranked = ordered_results(results)
    if ranked.empty:
        return "—"
    first = ranked[ranked["position"] == 1]
    return (
        _display_driver(first.iloc[0].get("driver_number"), names)
        if not first.empty
        else "—"
    )


def _named_results(results: pd.DataFrame, drivers: pd.DataFrame) -> pd.DataFrame:
    public = ordered_results(results)
    names, teams = _driver_names(drivers), _team_names(drivers)
    if "driver_number" in public:
        public["Pilot"] = public["driver_number"].map(
            lambda number: _display_driver(number, names)
        )
        public["Team"] = public["driver_number"].map(
            lambda number: teams.get(_as_int(number), "Unknown team")
        )
    public["Position"] = pd.to_numeric(public.get("position"), errors="coerce")
    return public


def _best_lap_chart(
    laps: pd.DataFrame, drivers: pd.DataFrame, title: str, limit: int | None = None
) -> None:
    """Plot each driver's validated best lap once, ordered by exact lap time."""
    comparison = best_lap_comparison(laps, _driver_names(drivers), _team_names(drivers))
    if comparison.empty:
        st.info("Não há melhores voltas válidas para comparar nesta sessão.")
        return
    if limit is not None:
        comparison = comparison.head(limit)
    comparison = comparison.sort_values("best_lap", kind="stable")
    order = comparison["Pilot"].tolist()
    low, high = comparison["best_lap"].min(), comparison["best_lap"].max()
    padding = max((high - low) * 0.08, 0.25)
    colors = _team_colors(drivers)
    team_colors = {
        team: colors.get(team, colors.get(team.casefold(), "#8a8f98"))
        for team in comparison["Team"].unique()
    }
    figure = px.scatter(
        comparison,
        x="best_lap",
        y="Pilot",
        color="Team",
        custom_data=["Team", "time_label", "delta_label"],
        category_orders={"Pilot": order},
        color_discrete_map=team_colors,
        title=title,
        labels={"best_lap": "Melhor volta (s; escala ampliada)"},
    )
    figure.update_traces(
        marker={"size": 11},
        hovertemplate=(
            "<b>%{y}</b><br>Equipe: %{customdata[0]}"
            "<br>Tempo: %{customdata[1]}<br>Delta: %{customdata[2]}<extra></extra>"
        ),
    )
    figure.update_xaxes(range=[max(0, low - padding), high + padding], tickformat=".3f")
    figure.update_yaxes(
        categoryorder="array", categoryarray=order, autorange="reversed"
    )
    _plot(figure, f"Melhores voltas individuais em {title}, ordenadas da mais rápida")


def _results_chart(
    results: pd.DataFrame, drivers: pd.DataFrame, title: str, session_type: str
) -> None:
    public = classification_table(
        results, _driver_names(drivers), _team_names(drivers), session_type
    )
    if public.empty:
        return
    st.subheader(f"Classificação oficial · {title} · {session_type}")
    st.dataframe(
        _styled_team_table(public, drivers),
        hide_index=True,
        height=min(640, 36 * (len(public) + 1) + 3),
        column_config={
            name: config
            for name, config in _classification_column_config().items()
            if name in public
        },
        alt=f"Classificação oficial de {session_type} em {title}, da P1 em diante",
    )


def _speed_max(laps: pd.DataFrame) -> float | None:
    columns = [
        column for column in ("i1_speed", "i2_speed", "st_speed") if column in laps
    ]
    values = (
        pd.concat([positive_numeric_values(laps[column]) for column in columns])
        if columns
        else pd.Series(dtype=float)
    )
    return float(values.max()) if not values.empty else None


def _session_grid(context: dict[str, object]) -> pd.DataFrame:
    grid_key = int(context.get("grid_key") or 0)
    if not grid_key:
        return pd.DataFrame()
    try:
        if context["source"] == "Online":
            return _frame(
                _online_endpoint(
                    int(context["year"]),
                    grid_key,
                    "starting_grid",
                    context.get("token"),
                )
            )
        path = (
            Path(str(context["data_dir"]))
            / str(context["year"])
            / str(grid_key)
            / "starting_grid.jsonl"
        )
        return _frame(
            _offline_endpoint(
                str(context["data_dir"]),
                int(context["year"]),
                grid_key,
                "starting_grid",
                path.stat().st_mtime_ns if path.exists() else 0,
            )
        )
    except OpenF1Error as exc:
        if context["source"] == "Online":
            _fallback(
                f"A OpenF1 está indisponível. Mudamos para os dados locais. ({exc})"
            )
        return pd.DataFrame()


# Fetch only the selected session's endpoints, cached for one minute.
def _executive() -> None:
    context = _context()
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    names = _driver_names(drivers)
    durations = (
        positive_numeric_values(laps["lap_duration"])
        if "lap_duration" in laps
        else pd.Series(dtype=float)
    )
    fastest_time = float(durations.min()) if not durations.empty else None
    speed = _speed_max(laps)
    sessions = context["sessions"]
    race_count = int(
        sessions.loc[sessions["session_type"] == "Race", "meeting_key"].nunique()
    )
    champ_drivers = data.get("championship_drivers", pd.DataFrame())
    champ_teams = data.get("championship_teams", pd.DataFrame())
    leader = "—"
    if not champ_drivers.empty and {"position_current", "driver_number"}.issubset(
        champ_drivers.columns
    ):
        champ_drivers = champ_drivers.copy()
        champ_drivers["position_current"] = pd.to_numeric(
            champ_drivers["position_current"], errors="coerce"
        )
        champ_drivers = champ_drivers.dropna(subset=["position_current"]).sort_values(
            "position_current", kind="stable"
        )
    if not champ_drivers.empty and "position_current" in champ_drivers:
        row = champ_drivers.iloc[0]
        leader = _display_driver(row.get("driver_number"), names)
    team = "—"
    if not champ_teams.empty and {"position_current", "team_name"}.issubset(
        champ_teams.columns
    ):
        champ_teams = champ_teams.copy()
        champ_teams["position_current"] = pd.to_numeric(
            champ_teams["position_current"], errors="coerce"
        )
        champ_teams = champ_teams.dropna(subset=["position_current"]).sort_values(
            "position_current", kind="stable"
        )
        if not champ_teams.empty:
            team = str(champ_teams.iloc[0].get("team_name") or "—")
    fastest = best_laps(laps)
    fastest_driver = (
        _display_driver(fastest.iloc[0]["driver_number"], names)
        if not fastest.empty
        else "?"
    )
    grid = ordered_results(_session_grid(context))
    pole_rows = grid.loc[grid["position"] == 1] if "position" in grid else grid
    pole = (
        _display_driver(pole_rows.iloc[0].get("driver_number"), names)
        if not pole_rows.empty
        else "Indisponivel"
    )
    is_race = context["session_type"] == "Race"
    _metrics(
        [
            ("Vencedor" if is_race else "P1 oficial", _winner(results, names)),
            (
                "Pole position" if is_race else "Sess?o",
                pole if is_race else context["session_label"],
            ),
            ("Volta mais rapida", fastest_driver),
        ]
    )
    st.caption(
        f"Melhor tempo valido: {fastest_time:.3f} s. "
        "Atualizacao por minuto no modo Online."
        if fastest_time is not None
        else "Melhor tempo indispon?vel nesta sessao."
    )
    with st.expander("Indicadores da sessao e da temporada", expanded=False):
        _metrics(
            [
                ("GPs na temporada", race_count),
                (
                    "Pilotos na sessão",
                    drivers["driver_number"].nunique()
                    if "driver_number" in drivers
                    else 0,
                ),
                (
                    "Volta mais rápida na sessão",
                    f"{fastest_time:.3f} s" if fastest_time is not None else "—",
                ),
                (
                    "Maior velocidade na sessão",
                    f"{speed:.0f} km/h" if speed is not None else "—",
                ),
                ("Líder do campeonato", leader),
                ("Equipe líder", team),
                ("Sessões na temporada", sessions["session_key"].nunique()),
            ]
        )
    season_tab, session_tab = st.tabs(["Destaques da temporada", "Resultado da sessao"])
    with season_tab:
        _season_leaders(champ_drivers, drivers, context)
    with session_tab:
        _results_chart(
            results, drivers, str(context["gp_name"]), str(context["session_type"])
        )
        _best_lap_chart(
            laps, drivers, "Melhor volta valida por piloto - sessao selecionada", 10
        )


def _season_leaders(
    standings: pd.DataFrame, drivers: pd.DataFrame, context: dict[str, object]
) -> None:
    st.subheader(f"Os protagonistas de {context['year']}")
    st.caption(
        f"Campeonato de pilotos ate {context['gp_name']} - "
        "posicoes e pontos oficiais da etapa selecionada. "
        "Este painel mostra o campeonato completo, sem o filtro de equipe/piloto."
    )
    required = {"driver_number", "position_current", "points_current"}
    if standings.empty or not required.issubset(standings.columns):
        st.info(
            "Classificacao da temporada indisponivel nesta fonte ou sessao. "
            "Selecione uma corrida com dados oficiais de campeonato. "
            "Os resultados da sessao continuam na aba ao lado.",
            icon=":material/leaderboard:",
        )
        return
    ranking = standings.copy()
    for column in ("position_current", "points_current", "driver_number"):
        ranking[column] = pd.to_numeric(ranking[column], errors="coerce")
    ranking = ranking.dropna(subset=list(required))
    ranking = ranking.loc[
        (ranking["position_current"] > 0) & (ranking["points_current"] >= 0)
    ].sort_values("position_current", kind="stable")
    ranking = ranking.drop_duplicates("driver_number", keep="first")
    if ranking.empty:
        st.info("Nao ha posicoes e pontos validos para apresentar o campeonato.")
        return
    names, teams = _driver_names(drivers), _team_names(drivers)
    ranking["Pilot"] = ranking["driver_number"].map(
        lambda number: _display_driver(number, names)
    )
    ranking["Team"] = ranking["driver_number"].map(teams).fillna("Equipe indisponivel")
    for column, (_, row) in zip(
        st.columns(min(3, len(ranking))), ranking.head(3).iterrows(), strict=True
    ):
        with column, st.container(border=True):
            st.caption(f"P{int(row['position_current'])} / CAMPEONATO")
            st.subheader(row["Pilot"])
            st.caption(row["Team"])
            st.metric("Pontos oficiais", f"{row['points_current']:g}")
    limit = st.segmented_control(
        "Pilotos no ranking",
        ["Top 10", "Todos"],
        default="Top 10",
        key="executive_ranking_limit",
    )
    visible = ranking.head(10) if limit != "Todos" else ranking
    figure = px.bar(
        visible,
        x="points_current",
        y="Pilot",
        color="Team",
        orientation="h",
        text="points_current",
        custom_data=["position_current", "Team"],
        category_orders={"Pilot": visible["Pilot"].tolist()},
        color_discrete_map=TEAM_COLORS,
        title="A disputa pelo campeonato",
        labels={
            "points_current": "Pontos oficiais",
            "Pilot": "Piloto",
            "Team": "Equipe",
        },
    )
    figure.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "P%{customdata[0]} - %{y}<br>%{customdata[1]}<br>%{x} pontos<extra></extra>"
        ),
    )
    figure.update_layout(height=max(400, 30 * len(visible) + 150))
    _plot(figure, "Ranking oficial de pilotos por pontos, na ordem do campeonato")


def _races() -> None:
    context = _context()
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    names = _driver_names(drivers)
    grid = _session_grid(context)
    pole = "—"
    if not grid.empty and "position" in grid:
        grid = ordered_results(grid)
        row = grid[grid["position"] == 1]
        if not row.empty:
            pole = _display_driver(row.iloc[0].get("driver_number"), names)
    fastest_laps = best_laps(laps)
    fastest = (
        f"{_display_driver(fastest_laps.iloc[0]['driver_number'], names)} · "
        f"{fastest_laps.iloc[0]['best_lap']:.3f} s"
        if not fastest_laps.empty
        else "—"
    )
    speed = _speed_max(laps)
    _metrics(
        [
            ("Vencedor", _winner(results, names)),
            ("Pole position", pole),
            ("Volta mais rápida", fastest),
            ("Velocidade máxima", f"{speed:.0f} km/h" if speed is not None else "—"),
        ]
    )
    _results_chart(
        results, drivers, str(context["gp_name"]), str(context["session_type"])
    )
    positions = data.get("position", pd.DataFrame())
    evolution = position_history(positions)
    if not evolution.empty:
        evolution["Pilot"] = evolution["driver_number"].map(
            lambda value: _display_driver(value, names)
        )
        _plot(
            px.line(
                evolution,
                x="date",
                y="position",
                color="Pilot",
                title="Evolução da posição oficial na sessão",
                labels={"date": "Horário (UTC)", "position": "Posição"},
            ).update_yaxes(autorange="reversed", dtick=1),
            "Evolução das posições oficiais ao longo da sessão",
        )


def _drivers_page() -> None:
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    if laps.empty or "lap_duration" not in laps:
        st.info("Não há voltas disponíveis nesta sessão.")
        return
    names, teams = _driver_names(drivers), _team_names(drivers)
    valid = valid_laps(laps)
    summary = best_laps(valid)
    if summary.empty:
        st.info("Não há voltas válidas para comparar nesta sessão.")
        return
    summary["Pilot"] = summary["driver_number"].map(
        lambda value: _display_driver(value, names)
    )
    summary["Team"] = summary["driver_number"].map(
        lambda value: teams.get(_as_int(value), "Unknown team")
    )
    _plot(
        px.scatter(
            summary[
                [
                    column
                    for column in (
                        "average_lap",
                        "best_lap",
                        "laps",
                        "Pilot",
                        "Team",
                    )
                    if column in summary
                ]
            ],
            x="average_lap",
            y="best_lap",
            size="laps",
            color="Team",
            hover_name="Pilot",
            color_discrete_map=_team_colors(drivers),
            title="Ritmo médio e melhor volta",
            labels={"average_lap": "Tempo médio (s)", "best_lap": "Melhor volta (s)"},
        )
        .update_xaxes(tickformat=".3f")
        .update_yaxes(tickformat=".3f"),
        "Comparação de ritmo e melhores voltas entre pilotos",
    )
    if not results.empty and "position" in results:
        positions = results.set_index("driver_number")["position"]
        summary["Finish"] = summary["driver_number"].map(positions)
    speeds = _speed_max(laps)
    _metrics(
        [
            ("Pilotos", summary["Pilot"].nunique()),
            ("Velocidade máxima", f"{speeds:.0f} km/h" if speeds is not None else "—"),
            ("Voltas válidas", len(valid)),
        ]
    )
    st.dataframe(
        _styled_team_table(summary.drop(columns="driver_number"), drivers),
        hide_index=True,
        column_config={
            name: config
            for name, config in {
                "Pilot": st.column_config.TextColumn(
                    "Piloto", width="medium", pinned=True
                ),
                "Team": st.column_config.TextColumn("Equipe", width="small"),
                "average_lap": st.column_config.NumberColumn(
                    "Tempo médio (s)", format="%.3f", width="small"
                ),
                "best_lap": st.column_config.NumberColumn(
                    "Melhor volta (s)", format="%.3f", width="small"
                ),
                "laps": st.column_config.NumberColumn(
                    "Voltas válidas", format="%d", width="small"
                ),
                "Finish": st.column_config.NumberColumn(
                    "Posição final", format="%d", width="small"
                ),
            }.items()
            if name in summary
        },
        alt="Classificação e ritmo dos pilotos",
    )


def _teams_page() -> None:
    data, _, _, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    championship = data.get("championship_teams", pd.DataFrame())
    if not championship.empty and "team_name" in championship:
        ranking = championship.rename(
            columns={
                "team_name": "Team",
                "position_current": "Position",
                "points_current": "Points",
            }
        )
        if "Position" in ranking:
            ranking["Position"] = pd.to_numeric(ranking["Position"], errors="coerce")
            ranking = ranking.dropna(subset=["Position"]).sort_values(
                "Position", kind="stable"
            )
        else:
            ranking = ranking.sort_values("Team", kind="stable")
        ranking = ranking[
            [column for column in ("Position", "Team", "Points") if column in ranking]
        ]
        if "Points" in ranking:
            ranking["Points"] = pd.to_numeric(ranking["Points"], errors="coerce")
            ranking = ranking.dropna(subset=["Points"])
        if ranking.empty or "Points" not in ranking:
            st.info("A classificação oficial de equipes não tem pontos válidos.")
            return
        _plot(
            px.bar(
                ranking,
                x="Team",
                y="Points",
                color="Team",
                color_discrete_map=_team_colors(drivers),
                title="Pontos oficiais no campeonato de equipes",
            ),
            "Classificação atual do campeonato de equipes",
        )
        st.dataframe(
            _styled_team_table(ranking, drivers),
            hide_index=True,
            column_config={
                name: config
                for name, config in {
                    "Position": st.column_config.NumberColumn(
                        "Posição", format="%d", width="small", pinned=True
                    ),
                    "Team": st.column_config.TextColumn(
                        "Equipe", width="medium", pinned=True
                    ),
                    "Points": st.column_config.NumberColumn(
                        "Pontos", format="%.0f", width="small"
                    ),
                }.items()
                if name in ranking
            },
            alt="Classificação do campeonato de equipes",
        )
        return
    st.info(
        "A OpenF1 não forneceu a classificação oficial de equipes para esta sessão. "
        "Pontos não serão estimados apenas pela posição de chegada."
    )


def _laps_page() -> None:
    data, laps, _, stints = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    names = _driver_names(drivers)
    if laps.empty or "lap_duration" not in laps:
        st.info("Não há dados de volta nesta sessão.")
    else:
        valid = valid_laps(laps)
        valid["Pilot"] = valid["driver_number"].map(
            lambda value: _display_driver(value, names)
        )
        _best_lap_chart(valid, drivers, "Melhor volta válida por piloto", 20)
        st.caption(
            "Distribuição e setores usam voltas completas válidas; "
            "voltas de saída dos boxes foram excluídas."
        )
        _plot(
            px.histogram(
                valid[["lap_duration", "Pilot"]],
                x="lap_duration",
                nbins=35,
                title="Distribuição dos tempos de volta",
                labels={"lap_duration": "Tempo (s)"},
            ).update_xaxes(tickformat=".3f", title_text="Tempo por volta (s)"),
            "Distribuição dos tempos de volta",
        )
        sectors = [
            column
            for column in (
                "duration_sector_1",
                "duration_sector_2",
                "duration_sector_3",
            )
            if column in valid
        ]
        if sectors:
            long = valid.melt(
                id_vars=["Pilot"],
                value_vars=sectors,
                var_name="Sector",
                value_name="Seconds",
            )
            long["Seconds"] = positive_numeric_values(long["Seconds"]).reindex(
                long.index
            )
            long = long.dropna(subset=["Seconds"])
            long["Sector"] = (
                long["Sector"]
                .str.extract(r"(\d+)$")[0]
                .map(lambda value: f"Setor {value}")
            )
            if long.empty:
                sectors = []
        if sectors:
            heat = long.groupby(["Pilot", "Sector"])["Seconds"].mean().unstack()
            _plot(
                px.imshow(
                    heat,
                    aspect="auto",
                    color_continuous_scale="RdYlGn_r",
                    title="Ritmo médio por setor (s)",
                    labels={"x": "Setor", "y": "Piloto", "color": "Tempo (s)"},
                ),
                "Mapa de calor dos tempos médios de setor",
            )
    timeline = stint_timeline(stints, names)
    if not timeline.empty:
        if "compound" in timeline:
            timeline["Tyre"] = timeline["compound"].fillna("Não informado")
            _plot(
                px.bar(
                    timeline,
                    x="Stint length",
                    y="Pilot",
                    base="Start lap",
                    color="Tyre",
                    barmode="overlay",
                    custom_data=["Start lap", "End lap", "stint_number"],
                    title="Estratégia de pneus por volta",
                    labels={"Stint length": "Voltas", "Pilot": "Piloto"},
                )
                .update_traces(
                    hovertemplate=(
                        "%{y}<br>Stint %{customdata[2]} · voltas "
                        "%{customdata[0]}–%{customdata[1]}"
                        "<br>Composto: %{fullData.name}<extra></extra>"
                    )
                )
                .update_xaxes(title_text="Volta da corrida"),
                "Stints e compostos registrados por piloto na sequência real de voltas",
            )
        public = timeline.rename(
            columns={
                "stint_number": "Stint",
                "tyre_age_at_start": "Tyre age",
            }
        )
        public = public[
            [
                column
                for column in (
                    "Pilot",
                    "Stint",
                    "Tyre",
                    "Start lap",
                    "End lap",
                    "Tyre age",
                )
                if column in public
            ]
        ]
        st.dataframe(
            public,
            hide_index=True,
            column_config={
                name: config
                for name, config in {
                    "Pilot": st.column_config.TextColumn(
                        "Piloto", width="medium", pinned=True
                    ),
                    "Stint": st.column_config.NumberColumn(
                        "Stint", format="%d", width="small"
                    ),
                    "Tyre": st.column_config.TextColumn("Composto", width="small"),
                    "Start lap": st.column_config.NumberColumn(
                        "Volta inicial", format="%d", width="small"
                    ),
                    "End lap": st.column_config.NumberColumn(
                        "Volta final", format="%d", width="small"
                    ),
                    "Tyre age": st.column_config.NumberColumn(
                        "Idade inicial do pneu", format="%d", width="small"
                    ),
                }.items()
                if name in public
            },
            alt="Stints e compostos de pneus",
        )


def _results_page() -> None:
    context = _context()
    data, _, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    _results_chart(
        results, drivers, str(context["gp_name"]), str(context["session_type"])
    )
    grid = _session_grid(context)
    if not grid.empty and "position" in grid:
        grid = ordered_results(grid)
        pole = grid[grid["position"] == 1]
        if not pole.empty:
            _metrics(
                [
                    (
                        "Pole position",
                        _display_driver(
                            pole.iloc[0].get("driver_number"), _driver_names(drivers)
                        ),
                    )
                ]
            )
    names = _driver_names(drivers)
    for endpoint, label in (
        ("championship_drivers", "Campeonato de pilotos"),
        ("championship_teams", "Campeonato de equipes"),
    ):
        ranking = data.get(endpoint, pd.DataFrame())
        if ranking.empty:
            continue
        ranking = ranking.copy()
        if "driver_number" in ranking:
            ranking["Pilot"] = ranking["driver_number"].map(
                lambda value: _display_driver(value, names)
            )
        if "position_current" in ranking:
            ranking["position_current"] = pd.to_numeric(
                ranking["position_current"], errors="coerce"
            )
            ranking = ranking.dropna(subset=["position_current"]).sort_values(
                "position_current", kind="stable"
            )
        identity = "driver_number" if "driver_number" in ranking else "team_name"
        if identity in ranking:
            ranking = ranking.drop_duplicates(identity, keep="first")
        for column in ("points_current", "points_start"):
            if column in ranking:
                ranking[column] = pd.to_numeric(ranking[column], errors="coerce")
        rename = {
            "position_current": "Position",
            "points_current": "Points",
            "points_start": "Points before round",
            "team_name": "Team",
        }
        ranking = ranking.rename(columns=rename)
        columns = [
            column
            for column in ("Position", "Pilot", "Team", "Points", "Points before round")
            if column in ranking
        ]
        st.subheader(label)
        table = ranking[columns]
        table_config = {
            column: st.column_config.NumberColumn(
                column,
                format="%.0f",
                width="small",
                pinned=column == "Position",
            )
            for column in ("Position", "Points", "Points before round")
            if column in table
        }
        if "Pilot" in table:
            table_config["Pilot"] = st.column_config.TextColumn(
                "Piloto", width="medium", pinned=True
            )
        if "Team" in table:
            table_config["Team"] = st.column_config.TextColumn("Equipe", width="medium")
        st.dataframe(
            _styled_team_table(table, drivers),
            hide_index=True,
            column_config=table_config,
            alt=label,
        )
    comparison = _team_season_comparison(context, data)
    if not comparison.empty:
        comparison = comparison.copy()
        comparison["Points"] = pd.to_numeric(comparison["Points"], errors="coerce")
        comparison = comparison.dropna(subset=["Season", "Team", "Points"])
        comparison = comparison.drop_duplicates(["Season", "Team"], keep="last")
    if not comparison.empty:
        _plot(
            px.bar(
                comparison,
                x="Team",
                y="Points",
                color="Season",
                barmode="group",
                title="Comparação do campeonato de equipes",
            ),
            "Pontuação das equipes comparada entre temporadas",
        )
    if results.empty:
        st.info("Não há classificação publicada para esta sessão.")


def _team_season_comparison(
    context: dict[str, object], current_data: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    year = int(context["year"])
    previous_year = year - 1
    rows: list[dict[str, object]] = []
    if context["source"] == "Online":
        if previous_year < 2023:
            return pd.DataFrame()
        try:
            catalog = _online_catalog(previous_year, context.get("token"))
            _, sessions = _catalog_frames(catalog)
            races = sessions[sessions["session_type"] == "Race"]
            if races.empty:
                return pd.DataFrame()
            final_race = races.iloc[-1]
            standings = _online_endpoint(
                previous_year,
                int(final_race["session_key"]),
                "championship_teams",
                context.get("token"),
            )
        except OpenF1Error as exc:
            _fallback(
                f"A OpenF1 está indisponível. Mudamos para os arquivos locais. ({exc})"
            )
        for standing in standings:
            rows.append(
                {
                    "Season": str(previous_year),
                    "Team": standing.get("team_name", "Unknown team"),
                    "Points": standing.get("points_current"),
                }
            )
        current_standings = current_data.get("championship_teams", pd.DataFrame())
        if not current_standings.empty:
            for standing in current_standings.to_dict("records"):
                rows.append(
                    {
                        "Season": str(year),
                        "Team": standing.get("team_name", "Unknown team"),
                        "Points": standing.get("points_current"),
                    }
                )
        return pd.DataFrame(rows)

    data_dir = str(context["data_dir"])
    for season_year in (previous_year, year):
        if season_year not in context.get("offline_years", []):
            continue
        root = Path(data_dir) / str(season_year)
        fingerprint = tuple(
            sorted(
                (str(path), path.stat().st_mtime_ns) for path in root.rglob("*.jsonl")
            )
        )
        season = _offline_season(data_dir, season_year, fingerprint)
        catalog = FileRepository(Path(data_dir)).load_catalog(season_year)
        _, season_sessions = _catalog_frames(catalog)
        races = season_sessions[season_sessions["session_type"] == "Race"].copy()
        championship = season.get("championship_teams", pd.DataFrame())
        if (
            races.empty
            or championship.empty
            or not {"session_key", "team_name", "points_current"}.issubset(
                championship.columns
            )
        ):
            continue
        if "date_end" not in races:
            continue
        races["_date_end"] = pd.to_datetime(
            races["date_end"], utc=True, errors="coerce"
        )
        races = races.dropna(subset=["_date_end"])
        if races.empty:
            continue
        latest_race_key = _as_int(
            races.sort_values("_date_end").iloc[-1]["session_key"]
        )
        if latest_race_key is None:
            continue
        championship = championship.copy()
        championship["session_key"] = pd.to_numeric(
            championship["session_key"], errors="coerce"
        )
        championship["points_current"] = pd.to_numeric(
            championship["points_current"], errors="coerce"
        )
        latest_standings = championship[
            (championship["session_key"] == latest_race_key)
            & championship["points_current"].notna()
        ]
        rows.extend(
            {
                "Season": str(season_year),
                "Team": standing["team_name"],
                "Points": standing["points_current"],
            }
            for standing in latest_standings.to_dict("records")
        )
    return pd.DataFrame(rows)


def _render_page(page: str, renderer) -> None:
    st.session_state["_dashboard_context"]["page"] = page
    renderer()


def _executive_route() -> None:
    _render_page("Dashboard executivo", _executive)


def _races_route() -> None:
    _render_page("Corridas", _races)


def _drivers_route() -> None:
    _render_page("Pilotos", _drivers_page)


def _teams_route() -> None:
    _render_page("Equipes", _teams_page)


def _laps_route() -> None:
    _render_page("Voltas", _laps_page)


def _results_route() -> None:
    _render_page("Resultados", _results_page)


@st.fragment(run_every="60s")
def _auto_refresh() -> None:
    now = time.monotonic()
    last = st.session_state.get("_last_auto_refresh", now)
    st.session_state["_last_auto_refresh"] = now
    if now - last >= 55:
        st.rerun()


def _latest_available_session(sessions: pd.DataFrame) -> pd.Series:
    """Choose the latest session already started, including a live session."""
    if "date_start" not in sessions:
        return sessions.iloc[-1]
    dated = sessions.copy()
    dated["_start"] = pd.to_datetime(dated["date_start"], utc=True, errors="coerce")
    dated = dated.dropna(subset=["_start"])
    if dated.empty:
        return sessions.iloc[-1]
    current = pd.Timestamp.now(tz="UTC")
    started = dated[dated["_start"] <= current]
    return (
        started.sort_values("_start").iloc[-1]
        if not started.empty
        else dated.sort_values("_start").iloc[0]
    )


def main() -> None:
    data_dir = Path(os.environ.get("F1_OUTPUT_DIR", "data"))
    offline_years = available_years(data_dir)
    if st.session_state.pop("_force_offline", False):
        st.session_state["data_source"] = "Offline"
        fallback_years = snapshot_years(data_dir) or offline_years
        if fallback_years and st.session_state.get("season_year") not in fallback_years:
            st.session_state["season_year"] = fallback_years[0]
    message = st.session_state.pop("_fallback_message", None)
    if message:
        st.warning(message, title="Modo Offline ativado")
    with st.sidebar:
        st.markdown("## :red[FORMULA 1] · Analytics")
        default_source = None if "data_source" in st.session_state else "Online"
        mode = (
            st.segmented_control(
                "Fonte dos dados",
                ["Online", "Offline"],
                default=default_source,
                key="data_source",
            )
            or "Online"
        )
        st.caption("Temporada e sessao")
        if mode == "Offline":
            if not offline_years:
                st.warning(
                    "Não encontrei temporadas locais em `data/`.",
                    title="Sem dados offline",
                )
                return
            years = offline_years
        else:
            years = list(range(datetime.now(UTC).year, 2022, -1))
        if st.session_state.get("season_year") not in years:
            st.session_state["season_year"] = years[0]
        year = st.selectbox("Ano", years, index=0, key="season_year")
        if mode == "Online":
            try:
                token = _access_token()
                catalog = _online_catalog(int(year), token)
                with suppress(OSError, json.JSONDecodeError):
                    FileRepository(data_dir).save_catalog(int(year), catalog)
            except OpenF1Error as exc:
                _fallback(
                    "A OpenF1 está indisponível. Mudamos para os arquivos locais. "
                    f"({exc})"
                )
        else:
            token = None
            year_dir = data_dir / str(year)
            fingerprint = tuple(
                sorted(
                    (str(path), path.stat().st_mtime_ns)
                    for path in year_dir.rglob("*.jsonl")
                )
            )
            catalog = _offline_catalog(str(data_dir.resolve()), int(year), fingerprint)
        meetings, sessions = _catalog_frames(catalog)
        if meetings.empty or sessions.empty:
            st.warning(
                "Não há calendário ou sessões para esse ano.",
                title="Temporada indisponível",
            )
            return
        meeting_keys = meetings["meeting_key"].dropna().tolist()
        meeting_labels = dict(
            zip(meetings["meeting_key"], meetings["gp_label"], strict=False)
        )
        default_session = _latest_available_session(sessions)
        latest_meeting_key = default_session.get("meeting_key")
        meeting_key = st.selectbox(
            "Grande Prêmio",
            meeting_keys,
            index=(
                meeting_keys.index(latest_meeting_key)
                if latest_meeting_key in meeting_keys
                else len(meeting_keys) - 1
            ),
            format_func=lambda key: meeting_labels.get(key, "Grand Prix"),
            key=f"gp_filter_{year}",
        )
        event_sessions = sessions[sessions["meeting_key"] == meeting_key]
        types = event_sessions["session_type"].dropna().astype(str).unique().tolist()
        preferred = (
            str(default_session["session_type"])
            if default_session.get("meeting_key") == meeting_key
            and str(default_session.get("session_type")) in types
            else "Race"
            if "Race" in types
            else types[-1]
        )
        session_type = st.selectbox(
            "Tipo de sessão",
            types,
            index=types.index(preferred),
            key=f"session_type_filter_{year}_{meeting_key}",
        )
        typed = event_sessions[event_sessions["session_type"] == session_type]
        session_labels = dict(
            zip(typed["session_key"], typed["session_label"], strict=False)
        )
        session_keys = typed["session_key"].dropna().tolist()
        default_session_key = (
            _as_int(default_session.get("session_key"))
            if default_session.get("meeting_key") == meeting_key
            and str(default_session.get("session_type")) == session_type
            else _as_int(typed.iloc[-1].get("session_key"))
        )
        session_key = st.selectbox(
            "Sessão",
            session_keys,
            index=(
                session_keys.index(default_session_key)
                if default_session_key in session_keys
                else len(session_keys) - 1
            ),
            format_func=lambda key: session_labels.get(key, "Session"),
            key=f"session_filter_{year}_{meeting_key}_{session_type}",
        )
        try:
            if mode == "Online":
                driver_rows = _online_endpoint(
                    int(year), int(session_key), "drivers", token
                )
            else:
                driver_path = data_dir / str(year) / str(session_key) / "drivers.jsonl"
                driver_rows = _offline_endpoint(
                    str(data_dir.resolve()),
                    int(year),
                    int(session_key),
                    "drivers",
                    driver_path.stat().st_mtime_ns if driver_path.exists() else 0,
                )
        except OpenF1Error as exc:
            _fallback(
                f"A OpenF1 está indisponível. Mudamos para os arquivos locais. ({exc})"
            )
        driver_frame = _frame(driver_rows)
        names = _driver_names(driver_frame)
        teams = _team_names(driver_frame)
        with st.expander("Equipe e piloto", expanded=False):
            team_options = ["All teams", *sorted(set(teams.values()))]
            selected_team = st.selectbox(
                "Equipe",
                team_options,
                format_func=lambda value: (
                    "Todas as equipes" if value == "All teams" else value
                ),
            )
            numbers = [
                number
                for number, team in teams.items()
                if selected_team == "All teams" or team == selected_team
            ]
            selected_drivers = st.multiselect(
                "Piloto",
                numbers,
                format_func=lambda number: names.get(number, "Driver"),
                key="driver_filter",
            )

    message = st.session_state.pop("_fallback_message", None)
    if message:
        st.warning(message, title="Modo Offline ativado")
    gp = meetings[meetings["meeting_key"] == meeting_key].iloc[0]
    current = typed[typed["session_key"] == session_key].iloc[-1]
    grid_key = int(session_key)
    if session_type == "Race":
        qualifying_sessions = sessions[
            (sessions["meeting_key"] == meeting_key)
            & (sessions["session_type"] == "Qualifying")
        ]
        if qualifying_sessions.empty:
            qualifying_sessions = sessions[
                (sessions["meeting_key"] == meeting_key)
                & (sessions["session_type"] == "Sprint Qualifying")
            ]
        if not qualifying_sessions.empty:
            grid_key = _as_int(qualifying_sessions.iloc[-1]["session_key"]) or 0
        else:
            grid_key = 0
    st.session_state["_dashboard_context"] = {
        "source": mode,
        "year": int(year),
        "session_key": int(session_key),
        "session_type": str(session_type),
        "session_label": str(session_labels[session_key]),
        "gp_name": str(gp["gp_name"]),
        "grid_key": grid_key,
        "data_dir": str(data_dir.resolve()),
        "token": token,
        "selected_drivers": selected_drivers,
        "team": selected_team,
        "sessions": sessions,
        "meetings": meetings,
        "offline_years": offline_years,
        "page": "Dashboard executivo",
    }
    st.title(str(gp["gp_name"]))
    st.caption(f"{year} · {current['session_label']} · Fonte {mode}")
    page = st.navigation(
        [
            st.Page(
                _executive_route,
                title="Dashboard executivo",
                icon=":material/dashboard:",
                default=True,
            ),
            st.Page(_races_route, title="Corridas", icon=":material/flag:"),
            st.Page(_drivers_route, title="Pilotos", icon=":material/person:"),
            st.Page(_teams_route, title="Equipes", icon=":material/groups:"),
            st.Page(_laps_route, title="Voltas", icon=":material/timer:"),
            st.Page(_results_route, title="Resultados", icon=":material/leaderboard:"),
        ]
    )
    _auto_refresh()
    page.run()


def launch() -> int:
    """Run `streamlit run src/f1/dashboard.py` through the Poetry entrypoint."""
    app = Path(__file__).with_name("dashboard.py")
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address=0.0.0.0",
    ]
    if port := os.environ.get("PORT"):
        command.append(f"--server.port={port}")
    return subprocess.call(command)


if __name__ == "__main__":
    main()
