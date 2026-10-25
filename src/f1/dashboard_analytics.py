"""Normalize session records before dashboard calculations."""

import math

import pandas as pd


def valid_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Return complete laps with a driver and finite positive duration in seconds."""
    if not {"driver_number", "lap_duration"}.issubset(laps.columns):
        return laps.iloc[0:0].copy()

    normalized = laps.copy()
    normalized["driver_number"] = pd.to_numeric(
        normalized["driver_number"], errors="coerce"
    )
    normalized["lap_duration"] = pd.to_numeric(
        normalized["lap_duration"], errors="coerce"
    )
    duration = normalized["lap_duration"]
    finite = duration.map(
        lambda value: math.isfinite(value) if pd.notna(value) else False
    )
    valid = normalized["driver_number"].notna() & finite & duration.gt(0)
    if "is_pit_out_lap" in normalized:
        pit_out = (
            normalized["is_pit_out_lap"]
            .astype("string")
            .str.casefold()
            .isin({"true", "1"})
        )
        valid &= ~pit_out
    return normalized.loc[valid].copy()


def best_laps(laps: pd.DataFrame) -> pd.DataFrame:
    """Summarize valid laps per driver using the minimum duration as best lap."""
    valid = valid_laps(laps)
    if valid.empty:
        return pd.DataFrame(
            columns=["driver_number", "best_lap", "average_lap", "laps"]
        )
    return (
        valid.groupby("driver_number", as_index=False)
        .agg(
            best_lap=("lap_duration", "min"),
            average_lap=("lap_duration", "mean"),
            laps=("lap_duration", "count"),
        )
        .sort_values("best_lap", kind="stable")
        .reset_index(drop=True)
    )


def best_lap_comparison(
    laps: pd.DataFrame,
    driver_names: dict[int, str],
    driver_teams: dict[int, str],
) -> pd.DataFrame:
    """Prepare each driver's validated best lap and delta for comparison plots."""
    comparison = best_laps(laps)
    if comparison.empty:
        return comparison.assign(Pilot=pd.Series(dtype=str), Team=pd.Series(dtype=str))
    comparison["Pilot"] = comparison["driver_number"].map(
        lambda number: driver_names.get(int(number), f"Driver #{int(number)}")
    )
    comparison["Team"] = comparison["driver_number"].map(
        lambda number: driver_teams.get(int(number), "Unknown team")
    )
    comparison["delta"] = comparison["best_lap"] - comparison["best_lap"].min()
    comparison["time_label"] = comparison["best_lap"].map(
        lambda value: f"{value:.3f} s"
    )
    comparison["delta_label"] = comparison["delta"].map(lambda value: f"+{value:.3f} s")
    return comparison.sort_values("best_lap", kind="stable").reset_index(drop=True)


def classification_table(
    results: pd.DataFrame,
    driver_names: dict[int, str],
    driver_teams: dict[int, str],
    session_type: str,
) -> pd.DataFrame:
    """Present official session positions with fields appropriate to session type."""
    ranked = ordered_results(results)
    if ranked.empty:
        return pd.DataFrame(columns=["Position", "Pilot", "Team"])
    public = pd.DataFrame(
        {
            "Position": ranked["position"].astype("int64"),
            "Pilot": ranked["driver_number"].map(
                lambda number: driver_names.get(int(number), f"Driver #{int(number)}")
            ),
            "Team": ranked["driver_number"].map(
                lambda number: driver_teams.get(int(number), "Unknown team")
            ),
        },
        index=ranked.index,
    )
    kind = session_type.casefold()
    if "qualifying" in kind:
        durations = ranked.get("duration", pd.Series(index=ranked.index, dtype=object))
        gaps = ranked.get("gap_to_leader", pd.Series(index=ranked.index, dtype=object))
        for index, phase in enumerate(("Q1", "Q2", "Q3")):
            public[phase] = durations.map(
                lambda value, i=index: _format_seconds(_phase_value(value, i))
            )
            public[f"Delta {phase}"] = gaps.map(
                lambda value, i=index: _format_gap(_phase_value(value, i))
            )
    else:
        durations = ranked.get("duration", pd.Series(index=ranked.index, dtype=object))
        gaps = ranked.get("gap_to_leader", pd.Series(index=ranked.index, dtype=object))
        is_race = kind in {"race", "sprint"}
        formatter = _format_race_duration if is_race else _format_seconds
        public["Tempo total" if is_race else "Melhor volta"] = durations.map(formatter)
        public["Diferença"] = gaps.map(_format_gap)
        if "number_of_laps" in ranked:
            public["Voltas"] = pd.to_numeric(
                ranked["number_of_laps"], errors="coerce"
            ).map(
                lambda value: str(int(value)) if pd.notna(value) and value >= 0 else "—"
            )
    if {"dnf", "dns", "dsq"}.intersection(ranked.columns):
        public["Situação"] = ranked.apply(_result_status, axis=1)
    return public.reset_index(drop=True)


def _phase_value(value: object, index: int) -> object:
    """Read a qualifying phase without coercing missing data into a result."""
    if isinstance(value, (list, tuple)):
        return value[index] if len(value) > index else None
    if index == 0:
        return value
    return None


def _format_seconds(value: object) -> str:
    """Format seconds as a lap or race duration while preserving missing values."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or not math.isfinite(float(number)) or number < 0:
        return "—"
    minutes, seconds = divmod(float(number), 60)
    return f"{int(minutes)}:{seconds:06.3f}" if minutes else f"{seconds:.3f} s"


def _format_race_duration(value: object) -> str:
    """Format race elapsed time as hours, minutes, and seconds."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or not math.isfinite(float(number)) or number < 0:
        return "—"
    hours, remainder = divmod(float(number), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)}:{int(minutes):02d}:{seconds:06.3f}"


def _format_gap(value: object) -> str:
    """Format an official gap value without deriving one from other fields."""
    if isinstance(value, str):
        return value if value.strip() else "—"
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number) or not math.isfinite(float(number)) or number < 0:
        return "—"
    return "0.000 s" if number == 0 else f"+{number:.3f} s"


def _result_status(row: pd.Series) -> str:
    """Translate official result flags into a concise status label."""
    for field, label in (("dsq", "DSQ"), ("dns", "DNS"), ("dnf", "DNF")):
        value = str(row.get(field, "")).casefold()
        if value in {"true", "1"}:
            return label
    return "Classificado"


def position_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize official position samples, remove exact time duplicates, and sort."""
    required = {"date", "position", "driver_number"}
    if not required.issubset(frame.columns):
        return frame.iloc[0:0].copy()
    history = frame.copy()
    history["date"] = pd.to_datetime(history["date"], utc=True, errors="coerce")
    history["position"] = pd.to_numeric(history["position"], errors="coerce")
    history["driver_number"] = pd.to_numeric(history["driver_number"], errors="coerce")
    valid_position = (
        history["position"].map(
            lambda value: math.isfinite(value) if pd.notna(value) else False
        )
        & history["position"].gt(0)
        & history["position"].mod(1).eq(0)
    )
    history = history.loc[
        history["date"].notna() & history["driver_number"].notna() & valid_position
    ].copy()
    return (
        history.drop_duplicates(["driver_number", "date"], keep="last")
        .sort_values(["date", "driver_number"], kind="stable")
        .reset_index(drop=True)
    )


def stint_timeline(stints: pd.DataFrame, driver_names: dict[int, str]) -> pd.DataFrame:
    """Prepare available tyre stints in real lap order without inferring strategy."""
    required = {"driver_number", "lap_start", "lap_end"}
    if not required.issubset(stints.columns):
        return stints.iloc[0:0].copy()
    timeline = stints.copy()
    timeline["driver_number"] = pd.to_numeric(
        timeline["driver_number"], errors="coerce"
    )
    timeline["Start lap"] = pd.to_numeric(timeline["lap_start"], errors="coerce")
    timeline["End lap"] = pd.to_numeric(timeline["lap_end"], errors="coerce")
    timeline = timeline.dropna(subset=["driver_number", "Start lap", "End lap"])
    timeline = timeline.loc[timeline["End lap"] >= timeline["Start lap"]].copy()
    if "stint_number" in timeline:
        timeline["stint_number"] = pd.to_numeric(
            timeline["stint_number"], errors="coerce"
        )
        numbered = timeline["stint_number"].notna()
        timeline = pd.concat(
            [
                timeline.loc[~numbered],
                timeline.loc[numbered].drop_duplicates(
                    ["driver_number", "stint_number"], keep="last"
                ),
            ]
        )
    timeline["Pilot"] = timeline["driver_number"].map(
        lambda number: driver_names.get(int(number), f"Driver #{int(number)}")
    )
    timeline["Stint length"] = timeline["End lap"] - timeline["Start lap"] + 1
    return timeline.sort_values(
        ["driver_number", "Start lap", "End lap"], kind="stable"
    ).reset_index(drop=True)


def ordered_results(results: pd.DataFrame) -> pd.DataFrame:
    """Normalize and deduplicate official results by driver and position.

    When a driver appears more than once, retain the best valid official
    position. Rows without a usable driver number or positive integer position
    cannot be ranked and are omitted.
    """
    if not {"driver_number", "position"}.issubset(results.columns):
        return results.iloc[0:0].copy()

    normalized = results.copy()
    normalized["driver_number"] = pd.to_numeric(
        normalized["driver_number"], errors="coerce"
    )
    position = pd.to_numeric(normalized["position"], errors="coerce")
    valid = position.map(
        lambda value: math.isfinite(value) if pd.notna(value) else False
    )
    valid &= position.gt(0) & position.mod(1).eq(0)
    normalized["position"] = position
    normalized = normalized.loc[
        normalized["driver_number"].notna() & valid
    ].sort_values(["position", "driver_number"], kind="stable")
    return normalized.drop_duplicates("driver_number", keep="first").reset_index(
        drop=True
    )


def positive_numeric_values(values: pd.Series) -> pd.Series:
    """Coerce a measurement column and discard non-finite or non-positive data."""
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric.map(
        lambda value: math.isfinite(value) if pd.notna(value) else False
    )
    return numeric.loc[finite & numeric.gt(0)]


def filter_driver_rows(frame: pd.DataFrame, selected: list[int]) -> pd.DataFrame:
    """Filter endpoint rows by driver, accepting numeric identifiers as strings."""
    if not selected or "driver_number" not in frame:
        return frame.copy()
    driver_numbers = pd.to_numeric(frame["driver_number"], errors="coerce")
    return frame.loc[driver_numbers.isin(selected)].copy()
