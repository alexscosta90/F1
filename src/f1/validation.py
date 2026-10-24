"""Regras de qualidade para registros de entrada da API."""

from collections.abc import Mapping, Sequence


def validate_records(
    records: Sequence[object], *, expected_session_key: int | None = None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Separa registros aceitos dos rejeitados com motivo rastreável.

    Linhas não-objeto e linhas de outra sessão são rejeitadas; campos extras e
    nulos são mantidos porque os schemas da fonte variam entre sessões.
    """
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            rejected.append(
                {"_source_record": record, "_rejection_reason": "expected_json_object"}
            )
        elif expected_session_key is not None and record.get("session_key") not in (
            None,
            expected_session_key,
        ):
            rejected.append(
                {
                    **record,
                    "_rejection_reason": "session_key_mismatch",
                    "_source_index": index,
                }
            )
        else:
            accepted.append(dict(record))
    return accepted, rejected
