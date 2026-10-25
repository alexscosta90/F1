import json
from pathlib import Path

from f1.dashboard_data import available_years, load_season


def test_available_years_lists_only_numeric_directories(tmp_path: Path) -> None:
    (tmp_path / "2024").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "2023").mkdir()

    assert available_years(tmp_path) == [2024, 2023]


def test_load_season_reads_jsonl_and_manifest_without_network(tmp_path: Path) -> None:
    session_dir = tmp_path / "2024" / "1001"
    session_dir.mkdir(parents=True)
    (session_dir / "manifest.jsonl").write_text(
        json.dumps(
            {
                "session_key": 1001,
                "metadata": {
                    "meeting_key": 77,
                    "session_name": "Race",
                    "session_type": "Race",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (session_dir / "laps.jsonl").write_text(
        '{"session_key":1001,"driver_number":1,"lap_duration":90.5}\n',
        encoding="utf-8",
    )
    (session_dir / "laps.rejected.jsonl").write_text(
        '{"session_key":1002}\n', encoding="utf-8"
    )

    result = load_season(tmp_path, 2024)

    assert result["laps"] == [
        {"session_key": 1001, "driver_number": 1, "lap_duration": 90.5}
    ]
    assert result["sessions"][0]["meeting_label"] == "Grand Prix"
    assert result["sessions"][0]["session_name"] == "Race"


def test_load_season_handles_missing_year(tmp_path: Path) -> None:
    assert load_season(tmp_path, 2024)["sessions"] == []


def test_snapshot_years_excludes_catalog_only_seasons(tmp_path: Path) -> None:
    from f1.dashboard_data import snapshot_years

    (tmp_path / "2026" / "_catalog").mkdir(parents=True)
    session = tmp_path / "2024" / "99"
    session.mkdir(parents=True)
    (session / "drivers.jsonl").write_text('{"driver_number": 16}\n', encoding="utf-8")
    assert snapshot_years(tmp_path) == [2024]
    assert snapshot_years(tmp_path / "missing") == []


def test_session_snapshots_indexes_only_nonempty_supported_endpoints(
    tmp_path: Path,
) -> None:
    from f1.dashboard_data import session_snapshots

    session = tmp_path / "2024" / "99"
    session.mkdir(parents=True)
    (session / "laps.jsonl").write_text('{"driver_number": 4}\n', encoding="utf-8")
    (session / "stints.jsonl").write_text("", encoding="utf-8")
    (session / "manifest.jsonl").write_text("{}", encoding="utf-8")
    (session.parent / "_catalog").mkdir()
    assert session_snapshots(tmp_path, 2024) == {99: {"laps"}}
    assert session_snapshots(tmp_path, 2025) == {}
