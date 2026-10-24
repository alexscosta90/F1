"""Leitura local dos snapshots JSONL usados pelo dashboard."""

import json
from collections.abc import Iterator
from pathlib import Path


def available_years(data_dir: Path) -> list[int]:
    """Lista temporadas locais que contenham pelo menos uma sessão."""
    if not data_dir.exists():
        return []
    return sorted(
        (
            int(path.name)
            for path in data_dir.iterdir()
            if path.is_dir() and path.name.isdigit()
        ),
        reverse=True,
    )


def _read_jsonl(path: Path) -> Iterator[dict[str, object]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value


def load_season(data_dir: Path, year: int) -> dict[str, list[dict[str, object]]]:
    """Carrega endpoints e metadados de sessão apenas do diretório local."""
    season_dir = data_dir / str(year)
    records: dict[str, list[dict[str, object]]] = {}
    manifests: list[dict[str, object]] = []
    for session_dir in sorted(season_dir.iterdir()) if season_dir.exists() else []:
        if not session_dir.is_dir():
            continue
        for endpoint_file in session_dir.glob("*.jsonl"):
            if endpoint_file.name == "manifest.jsonl":
                manifests.extend(_read_jsonl(endpoint_file))
            elif not endpoint_file.name.endswith(".rejected.jsonl"):
                records.setdefault(endpoint_file.stem, []).extend(
                    _read_jsonl(endpoint_file)
                )

    sessions: dict[object, dict[str, object]] = {}
    meetings: dict[object, dict[str, object]] = {}
    catalog_dir = season_dir / "_catalog"
    for record in _read_jsonl(catalog_dir / "sessions.jsonl"):
        key = record.get("session_key")
        if key is not None:
            sessions[key] = dict(record)
    for record in _read_jsonl(catalog_dir / "meetings.jsonl"):
        key = record.get("meeting_key")
        if key is not None:
            meetings[key] = dict(record)
    for manifest in manifests:
        metadata = manifest.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        session = {
            "year": year,
            "session_key": manifest.get("session_key"),
            "meeting_key": metadata.get("meeting_key"),
            "session_name": metadata.get("session_name") or "Sessão",
            "session_type": metadata.get("session_type") or "Desconhecida",
        }
        key = session["session_key"]
        if key is not None and key not in sessions:
            sessions[key] = session
    for session in sessions.values():
        meeting_key = session.get("meeting_key")
        meeting = meetings.get(meeting_key, {})
        session["meeting_name"] = (
            meeting.get("meeting_name")
            or meeting.get("meeting_official_name")
            or "Grand Prix"
        )
        session["meeting_label"] = session["meeting_name"]

    if "drivers" in records:
        unique_drivers: dict[object, dict[str, object]] = {}
        for driver in records["drivers"]:
            number = driver.get("driver_number")
            if number is not None:
                unique_drivers[number] = {
                    key: driver[key]
                    for key in (
                        "driver_number",
                        "full_name",
                        "name_acronym",
                        "team_name",
                    )
                    if key in driver
                }
        records["drivers"] = list(unique_drivers.values())
    records["sessions"] = list(sessions.values())
    records["meetings"] = list(meetings.values())
    return records
