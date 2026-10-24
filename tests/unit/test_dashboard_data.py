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
