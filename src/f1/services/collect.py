"""Coordenação do fluxo de coleta para uma sessão OpenF1."""

import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from f1.ingestion.client import OpenF1Client
from f1.storage import write_jsonl_atomic
from f1.transformations import normalize_records
from f1.validation import validate_records

logger = logging.getLogger(__name__)


def collect_session(
    client: OpenF1Client,
    *,
    session_key: int,
    year: int,
    endpoints: Sequence[str],
    output_dir: Path,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Consulta, valida, normaliza e grava os endpoints de uma sessão.

    Todos os endpoints são lidos e validados antes da primeira gravação; cada
    arquivo individual é substituído atomicamente para permitir reprocessamento.
    """
    run_id = str(uuid.uuid4())
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    logger.info("Início run_id=%s year=%s session_key=%s", run_id, year, session_key)
    pending: dict[str, list[dict[str, object]]] = {}
    rejected_rows: dict[str, list[dict[str, object]]] = {}
    counts: dict[str, dict[str, int]] = {}
    skipped: dict[str, str] = {}
    session_type = metadata.get("session_type") if metadata else None
    for endpoint in endpoints:
        if endpoint == "starting_grid" and session_type not in (
            "Qualifying",
            "Sprint Qualifying",
        ):
            skipped[endpoint] = (
                "starting_grid requer uma sessão de qualificação; "
                f"session_type recebido: {session_type!r}"
            )
            logger.info(
                "run_id=%s endpoint=%s ignorado: %s",
                run_id,
                endpoint,
                skipped[endpoint],
            )
            continue
        raw = client.get(endpoint, {"session_key": session_key})
        accepted, rejected = validate_records(raw, expected_session_key=session_key)
        pending[endpoint] = normalize_records(accepted)
        rejected_rows[endpoint] = rejected
        counts[endpoint] = {
            "read": len(raw),
            "accepted": len(accepted),
            "rejected": len(rejected),
        }
        if rejected:
            logger.warning(
                "run_id=%s endpoint=%s rejeitados=%d", run_id, endpoint, len(rejected)
            )

    session_dir = output_dir / str(year) / str(session_key)
    saved: dict[str, int] = {}
    for endpoint, rows in pending.items():
        saved[endpoint] = write_jsonl_atomic(session_dir / f"{endpoint}.jsonl", rows)
        if rejected_rows[endpoint]:
            write_jsonl_atomic(
                session_dir / f"{endpoint}.rejected.jsonl", rejected_rows[endpoint]
            )
        elif (session_dir / f"{endpoint}.rejected.jsonl").exists():
            (session_dir / f"{endpoint}.rejected.jsonl").unlink()
    manifest = {
        "run_id": run_id,
        "contract_version": "1",
        "started_at": started_at,
        "year": year,
        "session_key": session_key,
        "endpoints": list(endpoints),
        "skipped": skipped,
        "source": "https://api.openf1.org/v1",
        "filters": {"session_key": session_key},
        "counts": counts,
        "written": saved,
        "metadata": dict(metadata or {}),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    write_jsonl_atomic(session_dir / "manifest.jsonl", [manifest])
    logger.info(
        "Fim run_id=%s session_key=%s lidos=%d aceitos=%d gravados=%d duração_s=%.3f",
        run_id,
        session_key,
        sum(item["read"] for item in counts.values()),
        sum(item["accepted"] for item in counts.values()),
        sum(saved.values()),
        manifest["duration_seconds"],
    )
    return manifest
