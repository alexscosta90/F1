"""Interface de linha de comando do pipeline F1."""

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from f1.config import DEFAULT_ENDPOINTS, Settings
from f1.ingestion.client import OpenF1Client, OpenF1Error
from f1.services.collect import collect_session
from f1.storage import write_jsonl_atomic


def build_parser() -> argparse.ArgumentParser:
    """Cria o parser com escopo de temporada e filtros opcionais."""
    parser = argparse.ArgumentParser(
        description="Coleta dados históricos da API OpenF1."
    )
    parser.add_argument("--year", type=int, required=True, help="Temporada a consultar")
    parser.add_argument("--meeting-key", type=int, help="Coletar somente uma etapa")
    parser.add_argument("--session-key", type=int, help="Coletar somente uma sessão")
    parser.add_argument(
        "--endpoints",
        default=",".join(DEFAULT_ENDPOINTS),
        help="Lista separada por vírgulas (padrão: %(default)s)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(os.environ.get("F1_OUTPUT_DIR", "data"))
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Descobre sessões e executa a coleta solicitada."""
    if not 1950 <= args.year <= 2100:
        raise ValueError("year deve estar entre 1950 e 2100")
    endpoints = tuple(
        item.strip() for item in args.endpoints.split(",") if item.strip()
    )
    if not endpoints or any(not item.replace("_", "").isalnum() for item in endpoints):
        raise ValueError("informe ao menos um endpoint válido")
    client = OpenF1Client(
        Settings(
            timeout_seconds=args.timeout,
            max_retries=args.retries,
            output_dir=args.output_dir,
            api_token=os.environ.get("F1_API_TOKEN"),
        )
    )
    meetings = client.get("meetings", {"year": args.year})
    all_meetings = list(meetings)
    if args.meeting_key is not None:
        meetings = [m for m in meetings if m.get("meeting_key") == args.meeting_key]
    meeting_keys = sorted(
        {m["meeting_key"] for m in meetings if isinstance(m.get("meeting_key"), int)}
    )
    sessions = client.get("sessions", {"year": args.year})
    all_sessions = list(sessions)
    catalog_dir = args.output_dir / str(args.year) / "_catalog"
    write_jsonl_atomic(catalog_dir / "meetings.jsonl", all_meetings)
    write_jsonl_atomic(catalog_dir / "sessions.jsonl", all_sessions)
    if meeting_keys:
        sessions = [s for s in sessions if s.get("meeting_key") in meeting_keys]
    if args.session_key is not None:
        sessions = [s for s in sessions if s.get("session_key") == args.session_key]
    if not sessions:
        raise OpenF1Error(f"Nenhuma sessão encontrada para year={args.year}")
    for session in sessions:
        session_key = session.get("session_key")
        if not isinstance(session_key, int):
            logging.warning("Sessão sem session_key foi ignorada")
            continue
        collect_session(
            client,
            session_key=session_key,
            year=args.year,
            endpoints=endpoints,
            output_dir=args.output_dir,
            metadata={
                "meeting_key": session.get("meeting_key"),
                "session_name": session.get("session_name"),
                "session_type": session.get("session_type"),
            },
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Executa o CLI e converte erros esperados em saída operacional clara."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return run(args)
    except (ValueError, OpenF1Error) as exc:
        logging.error("Execução encerrada: %s", exc)
        return 1
