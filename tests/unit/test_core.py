"""Testes determinísticos das regras locais do pipeline."""

import json
from pathlib import Path

import pytest

from f1.config import Settings
from f1.services.collect import collect_session
from f1.storage import write_jsonl_atomic
from f1.transformations import normalize_records
from f1.validation import validate_records


def test_settings_reject_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        Settings(timeout_seconds=0)


def test_validation_preserves_optional_fields_and_rejects_other_session() -> None:
    accepted, rejected = validate_records(
        [{"session_key": 10, "optional": None}, {"session_key": 11}, "bad"],
        expected_session_key=10,
    )
    assert accepted == [{"session_key": 10, "optional": None}]
    assert len(rejected) == 2


def test_normalization_converts_offset_to_utc_and_preserves_original() -> None:
    rows = normalize_records([{"date": "2024-01-01T01:00:00+01:00", "value": 2}])
    assert rows[0]["date"] == "2024-01-01T00:00:00Z"
    assert rows[0]["_source_dates"] == {"date": "2024-01-01T01:00:00+01:00"}


def test_normalization_keeps_unparseable_dates() -> None:
    assert normalize_records([{"date": "unknown"}]) == [{"date": "unknown"}]


def test_write_jsonl_is_repeatable_and_replaces_complete_file(tmp_path: Path) -> None:
    target = tmp_path / "2024" / "1" / "laps.jsonl"
    assert write_jsonl_atomic(target, [{"lap_number": 1}]) == 1
    assert write_jsonl_atomic(target, [{"lap_number": 2}]) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == {"lap_number": 2}


def test_collection_writes_normalized_data_and_rejected_rows(tmp_path: Path) -> None:
    class FakeClient:
        """Cliente local fixo para cobrir o fluxo sem acessar a rede."""

        def get(
            self, endpoint: str, filters: dict[str, int]
        ) -> list[dict[str, object]]:
            assert endpoint == "laps"
            assert filters == {"session_key": 7}
            return [
                {"session_key": 7, "date": "2024-01-01T01:00:00+01:00"},
                {"session_key": 8},
            ]

    manifest = collect_session(
        FakeClient(),  # type: ignore[arg-type]
        session_key=7,
        year=2024,
        endpoints=["laps"],
        output_dir=tmp_path,
    )
    target = tmp_path / "2024" / "7"
    rows = [
        json.loads(line) for line in (target / "laps.jsonl").read_text().splitlines()
    ]
    rejected = [
        json.loads(line)
        for line in (target / "laps.rejected.jsonl").read_text().splitlines()
    ]
    assert rows[0]["date"] == "2024-01-01T00:00:00Z"
    assert rejected[0]["_rejection_reason"] == "session_key_mismatch"
    assert manifest["counts"]["laps"]["rejected"] == 1  # type: ignore[index]


def test_collection_skips_starting_grid_for_non_qualifying_session(
    tmp_path: Path,
) -> None:
    class FakeClient:
        """Cliente que falha se o grid for consultado fora de qualificação."""

        def get(
            self, endpoint: str, filters: dict[str, int]
        ) -> list[dict[str, object]]:
            assert endpoint == "laps"
            assert filters == {"session_key": 7}
            return []

    manifest = collect_session(
        FakeClient(),  # type: ignore[arg-type]
        session_key=7,
        year=2024,
        endpoints=["starting_grid", "laps"],
        output_dir=tmp_path,
        metadata={"session_type": "Practice"},
    )
    assert manifest["skipped"] == {
        "starting_grid": "starting_grid requer uma sessão de qualificação; "
        "session_type recebido: 'Practice'"
    }


def test_collection_queries_starting_grid_for_qualifying_session(
    tmp_path: Path,
) -> None:
    class FakeClient:
        """Cliente que registra o filtro enviado ao endpoint de grid."""

        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, int]]] = []

        def get(
            self, endpoint: str, filters: dict[str, int]
        ) -> list[dict[str, object]]:
            self.calls.append((endpoint, filters))
            return [{"session_key": 7, "position": 1}]

    client = FakeClient()
    manifest = collect_session(
        client,  # type: ignore[arg-type]
        session_key=7,
        year=2024,
        endpoints=["starting_grid"],
        output_dir=tmp_path,
        metadata={"session_type": "Qualifying"},
    )
    assert client.calls == [("starting_grid", {"session_key": 7})]
    assert manifest["skipped"] == {}
