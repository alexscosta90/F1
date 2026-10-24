import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


def test_offline_dashboard_renders_without_openf1_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    year_dir = tmp_path / "2024"
    catalog = year_dir / "_catalog"
    session = year_dir / "99"
    catalog.mkdir(parents=True)
    session.mkdir()
    (catalog / "meetings.jsonl").write_text(
        json.dumps({"meeting_key": 5, "meeting_name": "Monaco Grand Prix"}) + "\n",
        encoding="utf-8",
    )
    (catalog / "sessions.jsonl").write_text(
        json.dumps(
            {
                "meeting_key": 5,
                "session_key": 99,
                "session_name": "Race",
                "session_type": "Race",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = {
        "drivers": [
            {
                "driver_number": 16,
                "full_name": "Charles Leclerc",
                "team_name": "Ferrari",
                "team_colour": "E8002D",
            }
        ],
        "laps": [
            {
                "session_key": 99,
                "driver_number": 16,
                "lap_duration": 90.2,
                "i1_speed": 290,
            }
        ],
        "session_result": [{"session_key": 99, "driver_number": 16, "position": 1}],
    }
    for endpoint, payload in rows.items():
        (session / f"{endpoint}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in payload), encoding="utf-8"
        )
    (session / "manifest.jsonl").write_text(
        json.dumps(
            {
                "session_key": 99,
                "metadata": {
                    "meeting_key": 5,
                    "session_name": "Race",
                    "session_type": "Race",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Offline dashboard attempted a network request")

    monkeypatch.setenv("F1_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("f1.ingestion.client.urlopen", fail_if_called)
    app = AppTest.from_file(
        Path(__file__).parents[2] / "src" / "f1" / "dashboard.py",
        default_timeout=30,
    )
    app.session_state["data_source"] = "Offline"
    app.session_state["season_year"] = 2024

    app.run()

    assert not app.exception
    assert app.title[0].value == "Monaco Grand Prix"
    assert len(app.metric) >= 6


def test_online_dashboard_uses_openf1_client_and_renders_latest_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = {
        "meetings": [{"meeting_key": 1200, "meeting_name": "Monaco Grand Prix"}],
        "sessions": [
            {
                "meeting_key": 1200,
                "session_key": 9900,
                "session_name": "Race",
                "session_type": "Race",
            }
        ],
        "drivers": [
            {
                "driver_number": 16,
                "full_name": "Charles Leclerc",
                "team_name": "Ferrari",
                "team_colour": "E8002D",
            }
        ],
        "laps": [
            {
                "session_key": 9900,
                "driver_number": 16,
                "lap_duration": 90.2,
                "i1_speed": 290,
            }
        ],
        "session_result": [{"session_key": 9900, "driver_number": 16, "position": 1}],
        "championship_drivers": [
            {
                "session_key": 9900,
                "driver_number": 16,
                "position_current": 1,
                "points_current": 25,
            }
        ],
        "championship_teams": [
            {
                "session_key": 9900,
                "team_name": "Ferrari",
                "position_current": 1,
                "points_current": 25,
            }
        ],
    }

    class FakeResponse:
        def __init__(self, body: object) -> None:
            self.body = json.dumps(body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self.body

    def fake_open(request: object, timeout: float) -> FakeResponse:
        del timeout
        endpoint = urlsplit(request.full_url).path.rsplit("/", maxsplit=1)[-1]  # type: ignore[attr-defined]
        return FakeResponse(payloads[endpoint])

    monkeypatch.setenv("F1_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("f1.ingestion.client.urlopen", fake_open)
    monkeypatch.setattr(
        "f1.ingestion.client.GLOBAL_RATE_LIMITER.acquire",
        lambda _endpoint: (0.0, 1),
    )
    app = AppTest.from_file(
        Path(__file__).parents[2] / "src" / "f1" / "dashboard.py",
        default_timeout=35,
    )
    app.session_state["data_source"] = "Online"
    app.session_state["season_year"] = 2026

    app.run(timeout=35)

    assert not app.exception
    assert app.title[0].value == "Monaco Grand Prix"
    assert any(
        metric.label == "Piloto líder" and metric.value == "Charles Leclerc (#16)"
        for metric in app.metric
    )


def test_online_failure_switches_to_local_data(tmp_path: Path, monkeypatch) -> None:
    st.cache_data.clear()
    st.cache_resource.clear()
    year_dir = tmp_path / "2026"
    catalog = year_dir / "_catalog"
    session = year_dir / "9900"
    catalog.mkdir(parents=True)
    session.mkdir()
    (catalog / "meetings.jsonl").write_text(
        '{"meeting_key":1200,"meeting_name":"Monaco Grand Prix"}\n',
        encoding="utf-8",
    )
    (catalog / "sessions.jsonl").write_text(
        '{"meeting_key":1200,"session_key":9900,"session_name":"Race","session_type":"Race"}\n',
        encoding="utf-8",
    )
    (session / "drivers.jsonl").write_text(
        '{"driver_number":16,"full_name":"Charles Leclerc","team_name":"Ferrari"}\n',
        encoding="utf-8",
    )

    def fail_online(request: object, timeout: float) -> None:
        del timeout
        raise HTTPError(request.full_url, 404, "temporarily unavailable", {}, None)  # type: ignore[attr-defined]

    monkeypatch.setenv("F1_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("f1.ingestion.client.urlopen", fail_online)
    app = AppTest.from_file(
        Path(__file__).parents[2] / "src" / "f1" / "dashboard.py",
        default_timeout=30,
    )
    app.session_state["data_source"] = "Online"
    app.session_state["season_year"] = 2026

    app.run()

    assert not app.exception
    assert app.segmented_control[0].value == "Offline"
    assert app.warning
    assert "OpenF1 está indisponível" in app.warning[0].value
