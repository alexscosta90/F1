import json
from pathlib import Path

from f1 import cli


def test_existing_collector_still_filters_and_saves_full_catalog(
    tmp_path: Path, monkeypatch
) -> None:
    sessions = [
        {
            "meeting_key": 10,
            "session_key": 101,
            "session_name": "Race",
            "session_type": "Race",
        },
        {
            "meeting_key": 11,
            "session_key": 111,
            "session_name": "Race",
            "session_type": "Race",
        },
    ]
    meetings = [
        {"meeting_key": 10, "meeting_name": "Monaco Grand Prix"},
        {"meeting_key": 11, "meeting_name": "Canadian Grand Prix"},
    ]

    class FakeClient:
        def __init__(self, _settings) -> None:
            pass

        def get(
            self, endpoint: str, filters: dict[str, int]
        ) -> list[dict[str, object]]:
            assert filters == {"year": 2024}
            return meetings if endpoint == "meetings" else sessions

    collected: list[int] = []
    monkeypatch.setattr(cli, "OpenF1Client", FakeClient)
    monkeypatch.setattr(
        cli,
        "collect_session",
        lambda *_args, session_key, **_kwargs: collected.append(session_key),
    )
    args = cli.build_parser().parse_args(
        [
            "--year",
            "2024",
            "--meeting-key",
            "10",
            "--session-key",
            "101",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert cli.run(args) == 0
    catalog_dir = tmp_path / "2024" / "_catalog"
    saved_meetings = [
        json.loads(line)
        for line in (catalog_dir / "meetings.jsonl").read_text().splitlines()
    ]
    saved_sessions = [
        json.loads(line)
        for line in (catalog_dir / "sessions.jsonl").read_text().splitlines()
    ]
    assert len(saved_meetings) == 2
    assert len(saved_sessions) == 2
    assert collected == [101]
