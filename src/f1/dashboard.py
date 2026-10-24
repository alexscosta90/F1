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

from f1.config import Settings
from f1.dashboard_data import available_years, load_season
from f1.dashboard_repository import FileRepository, OpenF1Repository
from f1.dashboard_service import DashboardService
from f1.ingestion.client import OpenF1Client, OpenF1Error

st.set_page_config(
    page_title="F1 | Race intelligence", page_icon=":material/speed:", layout="wide"
)

TEAM_FALLBACK_COLORS = {
    "ferrari": "#e8002d",
    "mercedes": "#00d2be",
    "mclaren": "#ff8000",
    "red bull": "#3671c6",
    "aston martin": "#229971",
    "williams": "#64c4ff",
    "alpine": "#ff87bc",
    "haas": "#b6babd",
    "rb": "#6692ff",
    "racing bulls": "#6692ff",
    "kick sauber": "#52e252",
    "sauber": "#52e252",
}
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
    colors = dict(TEAM_FALLBACK_COLORS)
    for row in drivers.to_dict("records") if not drivers.empty else []:
        if isinstance(row.get("team_name"), str) and isinstance(
            row.get("team_colour"), str
        ):
            colors[row["team_name"].lower()] = (
                f"#{row['team_colour'].removeprefix('#')}"
            )
    return colors


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
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        transition_duration=350,
        margin={"l": 12, "r": 12, "t": 54, "b": 12},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, alt=alt)


def _metrics(items: list[tuple[str, object]]) -> None:
    with st.container(horizontal=True):
        for label, value in items:
            st.metric(label, value, border=True)


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
        if selected and "driver_number" in frame:
            frame = frame[frame["driver_number"].isin(selected)]
        outputs.append(frame)
    return data, *outputs


def _winner(results: pd.DataFrame, names: dict[int, str]) -> str:
    if results.empty or "position" not in results:
        return "—"
    first = results[pd.to_numeric(results["position"], errors="coerce") == 1]
    return (
        _display_driver(first.iloc[0].get("driver_number"), names)
        if not first.empty
        else "—"
    )


def _named_results(results: pd.DataFrame, drivers: pd.DataFrame) -> pd.DataFrame:
    public = results.copy()
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


def _results_chart(results: pd.DataFrame, drivers: pd.DataFrame, title: str) -> None:
    if results.empty or "position" not in results:
        return
    public = (
        _named_results(results, drivers)
        .dropna(subset=["Position"])
        .sort_values("Position")
        .head(10)
    )
    if not public.empty:
        _plot(
            px.bar(
                public[["Pilot", "Team", "Position"]],
                x="Pilot",
                y="Position",
                color="Team",
                color_discrete_map=_team_colors(drivers),
                text="Position",
                title=f"Classificação · {title}",
            ).update_yaxes(autorange="reversed"),
            f"Classificação de pilotos em {title}",
        )


def _speed_max(laps: pd.DataFrame) -> float | None:
    columns = [
        column for column in ("i1_speed", "i2_speed", "st_speed") if column in laps
    ]
    values = (
        pd.concat(
            [pd.to_numeric(laps[column], errors="coerce") for column in columns]
        ).dropna()
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
    race_sessions = context["sessions"]
    race_sessions = race_sessions[race_sessions["session_type"] == "Race"]
    if context["source"] == "Offline":
        root = Path(str(context["data_dir"])) / str(context["year"])
        fingerprint = tuple(
            sorted(
                (str(path), path.stat().st_mtime_ns) for path in root.rglob("*.jsonl")
            )
        )
        season = _offline_season(
            str(context["data_dir"]), int(context["year"]), fingerprint
        )
        race_keys = race_sessions["session_key"].dropna().tolist()
        laps = season.get("laps", pd.DataFrame())
        results = season.get("session_result", pd.DataFrame())
        if "session_key" in laps:
            laps = laps[laps["session_key"].isin(race_keys)]
        if "session_key" in results:
            results = results[results["session_key"].isin(race_keys)]
        drivers = season.get("drivers", drivers)
        if not results.empty and {"position", "driver_number"}.issubset(
            results.columns
        ):
            point_values = {
                1: 25,
                2: 18,
                3: 15,
                4: 12,
                5: 10,
                6: 8,
                7: 6,
                8: 4,
                9: 2,
                10: 1,
            }
            point_rows = results.copy()
            point_rows["_points"] = (
                pd.to_numeric(point_rows["position"], errors="coerce")
                .map(point_values)
                .fillna(0)
            )
            team_map = _team_names(drivers)
            point_rows["_team"] = point_rows["driver_number"].map(
                lambda value: team_map.get(_as_int(value), "Unknown team")
            )
            context["season_driver_leader"] = (
                point_rows.groupby("driver_number")["_points"].sum().idxmax()
            )
            context["season_team_leader"] = (
                point_rows.groupby("_team")["_points"].sum().idxmax()
            )
    names = _driver_names(drivers)
    durations = (
        pd.to_numeric(laps.get("lap_duration"), errors="coerce")
        if "lap_duration" in laps
        else pd.Series(dtype=float)
    )
    valid = durations.dropna()
    fastest_time = float(valid.min()) if not valid.empty else None
    speed = _speed_max(laps)
    sessions = context["sessions"]
    race_count = int(
        sessions.loc[sessions["session_type"] == "Race", "meeting_key"].nunique()
    )
    champ_drivers = data.get("championship_drivers", pd.DataFrame())
    champ_teams = data.get("championship_teams", pd.DataFrame())
    leader = _winner(results, names)
    if not champ_drivers.empty and "position_current" in champ_drivers:
        row = champ_drivers.sort_values("position_current").iloc[0]
        leader = _display_driver(row.get("driver_number"), names)
    team = "—"
    if not champ_teams.empty and "position_current" in champ_teams:
        team = str(
            champ_teams.sort_values("position_current").iloc[0].get("team_name") or "—"
        )
    elif context.get("season_driver_leader") is not None:
        leader = _display_driver(context["season_driver_leader"], names)
        team = str(context.get("season_team_leader") or "—")
    elif leader != "—" and not results.empty:
        first = (
            results[pd.to_numeric(results["position"], errors="coerce") == 1]
            if "position" in results
            else pd.DataFrame()
        )
        team = (
            _team_names(drivers).get(_as_int(first.iloc[0].get("driver_number")), "—")
            if not first.empty
            else "—"
        )
    scope = "temporada" if context["source"] == "Offline" else str(context["gp_name"])
    st.caption(
        f"Voltas, velocidade e liderança calculadas para {scope}. "
        "A fonte online atualiza a cada minuto."
    )
    _metrics(
        [
            ("Grandes Prêmios", race_count),
            (
                "Pilotos na sessão",
                drivers["driver_number"].nunique() if "driver_number" in drivers else 0,
            ),
            (
                "Volta mais rápida",
                f"{fastest_time:.3f} s" if fastest_time is not None else "—",
            ),
            ("Maior velocidade", f"{speed:.0f} km/h" if speed is not None else "—"),
            ("Piloto líder", leader),
            ("Equipe líder", team),
            ("Sessões", len(sessions)),
        ]
    )
    if fastest_time is not None:
        top = (
            laps.assign(_time=durations)
            .dropna(subset=["_time"])
            .nsmallest(10, "_time")
            .copy()
        )
        top["Pilot"] = top["driver_number"].map(
            lambda value: _display_driver(value, names)
        )
        _plot(
            px.bar(
                top[["_time", "Pilot"]],
                x="_time",
                y="Pilot",
                orientation="h",
                title="Voltas mais rápidas da sessão",
                labels={"_time": "Tempo (s)"},
                color_discrete_sequence=["#e10600"],
            ).update_yaxes(categoryorder="total ascending"),
            "As dez voltas mais rápidas da sessão selecionada",
        )
    _results_chart(results, drivers, str(context["gp_name"]))


def _races() -> None:
    context = _context()
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    names = _driver_names(drivers)
    grid = _session_grid(context)
    pole = "—"
    if not grid.empty and "position" in grid:
        row = grid[pd.to_numeric(grid["position"], errors="coerce") == 1]
        if not row.empty:
            pole = _display_driver(row.iloc[0].get("driver_number"), names)
    duration = (
        pd.to_numeric(laps.get("lap_duration"), errors="coerce")
        if "lap_duration" in laps
        else pd.Series(dtype=float)
    )
    valid = duration.dropna()
    fastest = (
        f"{_display_driver(laps.loc[duration.idxmin()].get('driver_number'), names)} · "
        f"{valid.min():.3f} s"
        if not valid.empty
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
    _results_chart(results, drivers, str(context["gp_name"]))
    positions = data.get("position", pd.DataFrame())
    if not positions.empty and {"date", "position", "driver_number"}.issubset(
        positions.columns
    ):
        positions = positions.copy()
        positions["Position"] = pd.to_numeric(positions["position"], errors="coerce")
        positions["Pilot"] = positions["driver_number"].map(
            lambda value: _display_driver(value, names)
        )
        evolution = positions[["date", "Position", "Pilot"]].dropna(subset=["Position"])
        _plot(
            px.line(
                evolution.sort_values("date"),
                x="date",
                y="Position",
                color="Pilot",
                title="Evolução da corrida",
            ).update_yaxes(autorange="reversed"),
            "Evolução das posições ao longo da corrida",
        )


def _drivers_page() -> None:
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    if laps.empty or "lap_duration" not in laps:
        st.info("Não há voltas disponíveis nesta sessão.")
        return
    names, teams = _driver_names(drivers), _team_names(drivers)
    valid = laps.copy()
    valid["lap_duration"] = pd.to_numeric(valid["lap_duration"], errors="coerce")
    valid = valid.dropna(subset=["lap_duration"])
    summary = valid.groupby("driver_number", as_index=False).agg(
        best_lap=("lap_duration", "min"),
        average_lap=("lap_duration", "mean"),
        laps=("lap_duration", "count"),
    )
    summary["Pilot"] = summary["driver_number"].map(
        lambda value: _display_driver(value, names)
    )
    summary["Team"] = summary["driver_number"].map(
        lambda value: teams.get(_as_int(value), "Unknown team")
    )
    speed_columns = [
        column for column in ("i1_speed", "i2_speed", "st_speed") if column in valid
    ]
    if speed_columns:
        speed_rows = valid.melt(
            id_vars=["driver_number"],
            value_vars=speed_columns,
            value_name="speed",
        )
        speed_rows["speed"] = pd.to_numeric(speed_rows["speed"], errors="coerce")
        average_speed = speed_rows.groupby("driver_number")["speed"].mean()
        summary["average_speed"] = summary["driver_number"].map(average_speed)
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
        ),
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
        summary.drop(columns="driver_number"),
        hide_index=True,
        alt="Classificação e ritmo dos pilotos",
    )


def _teams_page() -> None:
    data, laps, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    teams = _team_names(drivers)
    championship = data.get("championship_teams", pd.DataFrame())
    if not championship.empty and "team_name" in championship:
        ranking = championship.rename(
            columns={
                "team_name": "Team",
                "position_current": "Position",
                "points_current": "Points",
            }
        )
        ranking = ranking[
            [column for column in ("Position", "Team", "Points") if column in ranking]
        ].sort_values("Position" if "Position" in ranking else "Team")
        _plot(
            px.bar(
                ranking,
                x="Team",
                y="Points",
                color="Team",
                color_discrete_map=_team_colors(drivers),
                title="Classificação atual do campeonato",
            ),
            "Classificação atual do campeonato de equipes",
        )
        st.dataframe(
            ranking, hide_index=True, alt="Classificação do campeonato de equipes"
        )
        return
    if results.empty or not {"driver_number", "position"}.issubset(results.columns):
        st.info("A classificação de equipes ainda não está disponível nesta sessão.")
        return
    table = results.copy()
    table["Team"] = table["driver_number"].map(
        lambda value: teams.get(_as_int(value), "Unknown team")
    )
    table["Position"] = pd.to_numeric(table["position"], errors="coerce")
    points = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
    table["Points"] = table["Position"].map(points).fillna(0)
    ranking = table.groupby("Team", as_index=False).agg(
        Points=("Points", "sum"), Finishers=("Position", "count")
    )
    ranking = ranking.sort_values("Points", ascending=False)
    _plot(
        px.bar(
            ranking,
            x="Team",
            y="Points",
            color="Team",
            color_discrete_map=_team_colors(drivers),
            title="Pontos por equipe",
        ),
        "Pontuação das equipes nesta sessão",
    )
    _metrics(
        [
            ("Equipe líder", ranking.iloc[0]["Team"]),
            ("Pontos", int(ranking.iloc[0]["Points"])),
            ("Equipes classificadas", len(ranking)),
        ]
    )
    st.dataframe(ranking, hide_index=True, alt="Desempenho das equipes")


def _laps_page() -> None:
    data, laps, _, stints = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    names = _driver_names(drivers)
    if laps.empty or "lap_duration" not in laps:
        st.info("Não há dados de volta nesta sessão.")
        return
    valid = laps.copy()
    valid["lap_duration"] = pd.to_numeric(valid["lap_duration"], errors="coerce")
    valid = valid.dropna(subset=["lap_duration"])
    valid["Pilot"] = valid["driver_number"].map(
        lambda value: _display_driver(value, names)
    )
    top = valid.nsmallest(20, "lap_duration")
    _plot(
        px.bar(
            top[["lap_duration", "Pilot"]],
            x="lap_duration",
            y="Pilot",
            orientation="h",
            title="Voltas mais rápidas",
            labels={"lap_duration": "Tempo (s)"},
            color_discrete_sequence=["#e10600"],
        ).update_yaxes(categoryorder="total ascending"),
        "As vinte voltas mais rápidas",
    )
    _plot(
        px.histogram(
            valid[["lap_duration", "Pilot"]],
            x="lap_duration",
            nbins=35,
            title="Distribuição dos tempos de volta",
            labels={"lap_duration": "Tempo (s)"},
        ),
        "Distribuição dos tempos de volta",
    )
    sectors = [
        column
        for column in ("duration_sector_1", "duration_sector_2", "duration_sector_3")
        if column in valid
    ]
    if sectors:
        long = valid.melt(
            id_vars=["Pilot"],
            value_vars=sectors,
            var_name="Sector",
            value_name="Seconds",
        )
        long["Seconds"] = pd.to_numeric(long["Seconds"], errors="coerce")
        heat = long.groupby(["Pilot", "Sector"])["Seconds"].mean().unstack()
        _plot(
            px.imshow(
                heat,
                aspect="auto",
                color_continuous_scale="RdYlGn_r",
                title="Ritmo médio por setor (s)",
            ),
            "Mapa de calor dos tempos médios de setor",
        )
    if not stints.empty:
        named = stints.copy()
        named["Pilot"] = named["driver_number"].map(
            lambda value: _display_driver(value, names)
        )
        public = named.rename(
            columns={
                "compound": "Tyre",
                "lap_start": "Start lap",
                "lap_end": "End lap",
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
        st.dataframe(public, hide_index=True, alt="Stints e compostos de pneus")


def _results_page() -> None:
    context = _context()
    data, _, results, _ = _selected_data()
    drivers = data.get("drivers", pd.DataFrame())
    _results_chart(results, drivers, str(context["gp_name"]))
    grid = _session_grid(context)
    if not grid.empty and "position" in grid:
        pole = grid[pd.to_numeric(grid["position"], errors="coerce") == 1]
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
            ranking = ranking.sort_values("position_current")
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
        st.dataframe(ranking[columns], hide_index=True, alt=label)
    comparison = _team_season_comparison(context, data)
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
        race_keys = season_sessions.loc[
            season_sessions["session_type"] == "Race", "session_key"
        ].tolist()
        results = season.get("session_result", pd.DataFrame())
        drivers = _team_names(season.get("drivers", pd.DataFrame()))
        if "session_key" in results:
            results = results[results["session_key"].isin(race_keys)]
        if results.empty or not {"driver_number", "position"}.issubset(results.columns):
            continue
        result_rows = results.copy()
        result_rows["Team"] = result_rows["driver_number"].map(
            lambda number, teams=drivers: teams.get(_as_int(number), "Unknown team")
        )
        result_rows["Points"] = (
            pd.to_numeric(result_rows["position"], errors="coerce")
            .map({1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1})
            .fillna(0)
        )
        team_points = result_rows.groupby("Team", as_index=False)["Points"].sum()
        team_points["Season"] = str(season_year)
        rows.extend(team_points.to_dict("records"))
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
        if offline_years and st.session_state.get("season_year") not in offline_years:
            st.session_state["season_year"] = offline_years[0]
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
        qualifying = sessions[
            (sessions["meeting_key"] == meeting_key)
            & sessions["session_type"].isin(["Qualifying", "Sprint Qualifying"])
        ]
        grid_key = (
            _as_int(qualifying.iloc[-1]["session_key"]) or 0
            if not qualifying.empty
            else 0
        )
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
