"""Repositories that supply the dashboard from OpenF1 or local JSONL files."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from f1.ingestion.client import OpenF1Client
from f1.storage import write_jsonl_atomic

Record = dict[str, object]


class DashboardRepository(Protocol):
    """Data access contract used by dashboard services."""

    def load_catalog(self, year: int) -> dict[str, list[Record]]: ...

    def load_endpoint(
        self, year: int, session_key: int, endpoint: str
    ) -> list[Record]: ...


class OpenF1Repository:
    """Online adapter. All API requests pass through the existing OpenF1 client."""

    def __init__(self, client: OpenF1Client) -> None:
        self._client = client

    def load_catalog(self, year: int) -> dict[str, list[Record]]:
        meetings = self._client.get("meetings", {"year": year})
        sessions = self._client.get("sessions", {"year": year})
        return {"meetings": meetings, "sessions": sessions}

    def load_endpoint(self, year: int, session_key: int, endpoint: str) -> list[Record]:
        del year
        return self._client.get(endpoint, {"session_key": session_key})


class FileRepository:
    """Offline adapter reading only the local JSONL snapshots."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def load_catalog(self, year: int) -> dict[str, list[Record]]:
        year_dir = self.data_dir / str(year)
        meetings = list(_read_jsonl(year_dir / "_catalog" / "meetings.jsonl"))
        sessions = list(_read_jsonl(year_dir / "_catalog" / "sessions.jsonl"))
        manifests: list[Record] = []
        for session_dir in year_dir.iterdir() if year_dir.exists() else []:
            if session_dir.is_dir() and session_dir.name != "_catalog":
                manifests.extend(_read_jsonl(session_dir / "manifest.jsonl"))
        if not sessions:
            sessions = [
                _session_from_manifest(year, manifest) for manifest in manifests
            ]
        if not meetings:
            meetings = _meetings_from_sessions(sessions)
        return {"meetings": meetings, "sessions": sessions}

    def load_endpoint(self, year: int, session_key: int, endpoint: str) -> list[Record]:
        path = self.data_dir / str(year) / str(session_key) / f"{endpoint}.jsonl"
        return list(_read_jsonl(path))

    def save_catalog(self, year: int, catalog: Mapping[str, Sequence[Record]]) -> None:
        """Persist official names locally so later offline sessions are friendly."""
        catalog_dir = self.data_dir / str(year) / "_catalog"
        for name in ("meetings", "sessions"):
            rows = list(catalog.get(name, []))
            path = catalog_dir / f"{name}.jsonl"
            if rows != list(_read_jsonl(path)):
                write_jsonl_atomic(path, rows)


def _read_jsonl(path: Path) -> Sequence[Record]:
    if not path.exists():
        return []
    rows: list[Record] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                record = json.loads(line)
                if isinstance(record, dict):
                    rows.append(record)
    return rows


def _session_from_manifest(year: int, manifest: Mapping[str, object]) -> Record:
    metadata = manifest.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return {
        "year": year,
        "session_key": manifest.get("session_key"),
        "meeting_key": metadata.get("meeting_key"),
        "session_name": metadata.get("session_name") or "Session",
        "session_type": metadata.get("session_type") or "Unknown",
    }


def _meetings_from_sessions(sessions: Sequence[Mapping[str, object]]) -> list[Record]:
    unique: dict[object, Record] = {}
    for session in sessions:
        meeting_key = session.get("meeting_key")
        if meeting_key is not None and meeting_key not in unique:
            unique[meeting_key] = {
                "meeting_key": meeting_key,
                "meeting_name": None,
                "meeting_official_name": None,
                "location": None,
                "country_name": None,
            }
    return list(unique.values())
