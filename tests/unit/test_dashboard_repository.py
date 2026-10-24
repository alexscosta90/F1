import json
from pathlib import Path

from f1.dashboard_repository import FileRepository, OpenF1Repository
from f1.dashboard_service import DashboardService


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, int]]] = []

    def get(self, endpoint: str, filters: dict[str, int]) -> list[dict[str, object]]:
        self.calls.append((endpoint, filters))
        return [{"endpoint": endpoint, **filters}]


def test_online_repository_uses_existing_client_for_catalog_and_endpoints() -> None:
    client = FakeClient()
    repository = OpenF1Repository(client)  # type: ignore[arg-type]
    service = DashboardService(repository)

    catalog = service.catalog(2024)
    laps = service.session_data(2024, 99, ["laps"])

    assert catalog["meetings"][0]["endpoint"] == "meetings"
    assert catalog["sessions"][0]["endpoint"] == "sessions"
    assert laps["laps"] == [{"endpoint": "laps", "session_key": 99}]
    assert client.calls == [
        ("meetings", {"year": 2024}),
        ("sessions", {"year": 2024}),
        ("laps", {"session_key": 99}),
    ]


def test_offline_repository_reads_saved_name_catalog_and_endpoint(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "2024" / "_catalog"
    session = tmp_path / "2024" / "99"
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
    (session / "laps.jsonl").write_text('{"lap_duration": 91.2}\n', encoding="utf-8")

    repository = FileRepository(tmp_path)

    assert (
        repository.load_catalog(2024)["meetings"][0]["meeting_name"]
        == "Monaco Grand Prix"
    )
    assert repository.load_endpoint(2024, 99, "laps") == [{"lap_duration": 91.2}]


def test_offline_repository_never_needs_catalog_or_network(tmp_path: Path) -> None:
    session = tmp_path / "2024" / "99"
    session.mkdir(parents=True)
    (session / "manifest.jsonl").write_text(
        json.dumps(
            {
                "session_key": 99,
                "metadata": {"meeting_key": 7, "session_type": "Race"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    catalog = FileRepository(tmp_path).load_catalog(2024)

    assert catalog["sessions"][0]["session_type"] == "Race"
    assert catalog["meetings"][0]["meeting_name"] is None


def test_save_catalog_persists_official_meeting_and_session_names(
    tmp_path: Path,
) -> None:
    repository = FileRepository(tmp_path)
    repository.save_catalog(
        2024,
        {
            "meetings": [{"meeting_key": 5, "meeting_name": "Monaco Grand Prix"}],
            "sessions": [
                {
                    "meeting_key": 5,
                    "session_key": 99,
                    "session_name": "Race",
                    "session_type": "Race",
                }
            ],
        },
    )

    loaded = repository.load_catalog(2024)

    assert loaded["meetings"][0]["meeting_name"] == "Monaco Grand Prix"
    assert loaded["sessions"][0]["session_name"] == "Race"
