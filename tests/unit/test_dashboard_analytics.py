import pandas as pd
import pytest

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


def test_best_laps_uses_minimum_finite_positive_duration_per_driver() -> None:
    laps = pd.DataFrame(
        [
            {"driver_number": "4", "lap_duration": "92.4"},
            {"driver_number": 4, "lap_duration": "90.1"},
            {"driver_number": 81, "lap_duration": "91.2"},
            {
                "driver_number": 81,
                "lap_duration": "60.0",
                "is_pit_out_lap": True,
            },
            {"driver_number": 81, "lap_duration": "invalid"},
            {"driver_number": 16, "lap_duration": 0},
            {"driver_number": None, "lap_duration": 80.0},
            {"driver_number": 55, "lap_duration": float("inf")},
        ]
    )

    result = best_laps(laps)

    assert result["driver_number"].tolist() == [4, 81]
    assert result["best_lap"].tolist() == [90.1, 91.2]
    assert result["laps"].tolist() == [2, 1]


def test_ordered_results_normalizes_positions_and_removes_duplicate_drivers() -> None:
    results = pd.DataFrame(
        [
            {"driver_number": "63", "position": "10", "status": "Finished"},
            {"driver_number": "81", "position": "2", "status": "Finished"},
            {"driver_number": "44", "position": "1", "status": "Finished"},
            {"driver_number": "81", "position": "7", "status": "Finished"},
            {"driver_number": "20", "position": "3", "status": "Finished"},
            {"driver_number": "16", "position": "DNS", "status": "Did not start"},
            {"driver_number": "55", "position": "2.5", "status": "Invalid"},
            {"driver_number": None, "position": "4", "status": "Invalid"},
        ]
    )

    ranked = ordered_results(results)

    assert ranked["driver_number"].tolist() == [44, 81, 20, 63]
    assert ranked["position"].tolist() == [1, 2, 3, 10]
    assert ranked["status"].tolist() == ["Finished"] * 4


def test_valid_laps_and_measurements_discard_invalid_values() -> None:
    laps = pd.DataFrame(
        [
            {"driver_number": "1", "lap_duration": "90.5"},
            {"driver_number": "2", "lap_duration": "nan"},
            {"driver_number": "3", "lap_duration": -1},
        ]
    )

    valid = valid_laps(laps)
    speeds = positive_numeric_values(pd.Series(["300", "invalid", 0, float("inf")]))

    assert valid["driver_number"].tolist() == [1]
    assert valid["lap_duration"].tolist() == [90.5]
    assert speeds.tolist() == [300]


def test_filter_driver_rows_matches_numeric_ids_stored_as_strings() -> None:
    rows = pd.DataFrame(
        [
            {"driver_number": "4", "lap_duration": 90},
            {"driver_number": "81", "lap_duration": 91},
            {"driver_number": "invalid", "lap_duration": 92},
        ]
    )

    filtered = filter_driver_rows(rows, [81])

    assert filtered["driver_number"].tolist() == ["81"]


def test_best_lap_plot_data_is_one_per_driver_sorted_with_exact_delta() -> None:
    laps = pd.DataFrame(
        [
            {"driver_number": "81", "lap_duration": "91.200"},
            {"driver_number": 4, "lap_duration": 92.4},
            {"driver_number": 4, "lap_duration": 90.1},
            {"driver_number": "81", "lap_duration": 90.8},
        ]
    )

    plotted = best_lap_comparison(
        laps,
        {4: "Lando Norris (#4)", 81: "Oscar Piastri (#81)"},
        {4: "McLaren", 81: "McLaren"},
    )

    assert plotted["driver_number"].tolist() == [4, 81]
    assert plotted["best_lap"].tolist() == [90.1, 90.8]
    assert plotted["delta"].tolist() == pytest.approx([0, 0.7])
    assert plotted["time_label"].tolist() == ["90.100 s", "90.800 s"]
    assert plotted["delta_label"].tolist() == ["+0.000 s", "+0.700 s"]


def test_classification_table_uses_official_positions_and_session_fields() -> None:
    results = pd.DataFrame(
        [
            {
                "driver_number": 81,
                "position": "2",
                "duration": [90.1, 89.5, None],
                "gap_to_leader": [0.1, 0.2, None],
            },
            {
                "driver_number": 4,
                "position": "1",
                "duration": [90.0, 89.3, 88.9],
                "gap_to_leader": [0, 0, 0],
            },
        ]
    )

    qualifying = classification_table(
        results,
        {4: "Lando Norris (#4)", 81: "Oscar Piastri (#81)"},
        {4: "McLaren", 81: "McLaren"},
        "Qualifying",
    )
    race = classification_table(
        pd.DataFrame(
            [
                {
                    "driver_number": 81,
                    "position": "2",
                    "duration": 5401.234,
                    "gap_to_leader": "+1 LAP(S)",
                    "number_of_laps": "57",
                    "dnf": False,
                    "dns": False,
                    "dsq": False,
                },
                {
                    "driver_number": 4,
                    "position": "1",
                    "duration": 5400.0,
                    "gap_to_leader": 0,
                    "number_of_laps": 58,
                    "dnf": False,
                    "dns": False,
                    "dsq": False,
                },
            ]
        ),
        {4: "Lando Norris (#4)", 81: "Oscar Piastri (#81)"},
        {4: "McLaren", 81: "McLaren"},
        "Race",
    )

    assert qualifying["Position"].tolist() == [1, 2]
    assert qualifying.loc[0, "Q3"] == "1:28.900"
    assert qualifying.loc[1, "Q3"] == "—"
    assert qualifying.loc[1, "Delta Q1"] == "+0.100 s"
    assert race["Pilot"].tolist() == ["Lando Norris (#4)", "Oscar Piastri (#81)"]
    assert race["Tempo total"].tolist() == ["1:30:00.000", "1:30:01.234"]
    assert race["Diferença"].tolist() == ["0.000 s", "+1 LAP(S)"]
    assert race["Voltas"].tolist() == ["58", "57"]
    assert race["Situação"].tolist() == ["Classificado", "Classificado"]


def test_classification_table_empty_input_returns_empty_official_view() -> None:
    result = classification_table(pd.DataFrame(), {}, {}, "Race")

    assert result.empty
    assert result.columns.tolist() == ["Position", "Pilot", "Team"]


def test_classification_table_keeps_official_non_finish_status_and_missing_times() -> (
    None
):
    results = pd.DataFrame(
        [
            {
                "driver_number": "4",
                "position": "1",
                "duration": "5400",
                "gap_to_leader": 0,
                "dnf": False,
                "dns": False,
                "dsq": False,
            },
            {
                "driver_number": "81",
                "position": "2",
                "duration": None,
                "gap_to_leader": None,
                "dnf": True,
                "dns": False,
                "dsq": False,
            },
        ]
    )

    table = classification_table(results, {}, {}, "Race")

    assert table["Position"].tolist() == [1, 2]
    assert table["Tempo total"].tolist() == ["1:30:00.000", "—"]
    assert table["Diferença"].tolist() == ["0.000 s", "—"]
    assert table["Situação"].tolist() == ["Classificado", "DNF"]


def test_position_history_sorts_samples_and_discards_invalid_rows() -> None:
    history = pd.DataFrame(
        [
            {"date": "2024-03-02T10:00:02Z", "position": "2", "driver_number": "4"},
            {"date": "2024-03-02T10:00:01Z", "position": "1", "driver_number": "4"},
            {"date": "2024-03-02T10:00:01Z", "position": 1, "driver_number": 4},
            {"date": "invalid", "position": 3, "driver_number": 81},
            {"date": "2024-03-02T10:00:03Z", "position": 1.5, "driver_number": 81},
        ]
    )

    ordered = position_history(history)

    assert ordered["position"].tolist() == [1, 2]
    assert ordered["driver_number"].tolist() == [4, 4]
    assert ordered["date"].is_monotonic_increasing


def test_stint_timeline_preserves_lap_sequence_and_handles_empty_input() -> None:
    stints = pd.DataFrame(
        [
            {
                "driver_number": "4",
                "stint_number": "2",
                "lap_start": "20",
                "lap_end": "35",
                "compound": "HARD",
            },
            {
                "driver_number": "4",
                "stint_number": "1",
                "lap_start": "1",
                "lap_end": "19",
                "compound": "MEDIUM",
            },
            {
                "driver_number": "81",
                "stint_number": "1",
                "lap_start": None,
                "lap_end": 10,
            },
        ]
    )

    timeline = stint_timeline(stints, {4: "Lando Norris (#4)"})
    empty = stint_timeline(pd.DataFrame(), {})

    assert timeline["Start lap"].tolist() == [1, 20]
    assert timeline["Stint length"].tolist() == [19, 16]
    assert timeline["compound"].tolist() == ["MEDIUM", "HARD"]
    assert empty.empty
