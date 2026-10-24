"""Transformações determinísticas dos registros OpenF1."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime


def normalize_records(
    records: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Normaliza campos de data ISO 8601 para UTC preservando a data original.

    Para cada campo cujo nome seja ``date`` ou termine em ``_date``, o valor
    original fica em ``_source_dates`` e o campo publicado recebe formato UTC.
    Datas não interpretáveis são mantidas sem alteração.
    """
    normalized: list[dict[str, object]] = []
    for record in records:
        row = dict(record)
        source_dates: dict[str, str] = {}
        for key, value in record.items():
            if (key == "date" or key.endswith("_date")) and isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
                source_dates[key] = value
                row[key] = (
                    parsed.replace(tzinfo=UTC)
                    if parsed.tzinfo is None
                    else parsed.astimezone(UTC)
                )
                row[key] = row[key].isoformat().replace("+00:00", "Z")
        if source_dates:
            row["_source_dates"] = source_dates
        normalized.append(row)
    return normalized
