"""Persistência JSONL local, atômica por endpoint e sessão."""

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path


def write_jsonl_atomic(path: Path, records: Sequence[Mapping[str, object]]) -> int:
    """Substitui um arquivo JSONL após escrever e sincronizar o conteúdo completo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            temporary_name = stream.name
            for record in records:
                stream.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return len(records)
