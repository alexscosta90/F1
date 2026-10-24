"""Configuração explícita para a coleta local da OpenF1."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENDPOINTS = ("drivers", "laps", "session_result", "starting_grid", "stints")


@dataclass(frozen=True, slots=True)
class Settings:
    """Parâmetros de rede e destino usados por uma execução."""

    base_url: str = "https://api.openf1.org/v1"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    output_dir: Path = Path("data")
    api_token: str | None = None

    def __post_init__(self) -> None:
        """Rejeita configurações que causariam chamadas sem limite útil."""
        if not self.base_url.startswith(("https://", "http://")):
            raise ValueError("base_url deve começar com http:// ou https://")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser maior que zero")
        if self.max_retries < 0:
            raise ValueError("max_retries não pode ser negativo")
