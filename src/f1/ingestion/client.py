"""Cliente HTTP pequeno e isolado para a API OpenF1."""

import json
import logging
import random
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from f1.config import Settings

logger = logging.getLogger(__name__)
type FilterValue = str | int | float
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
ERROR_BODY_LOG_LIMIT = 4096
RATE_WINDOW_SECONDS = 60.0
MAX_REQUESTS_PER_WINDOW = 28
MIN_REQUEST_INTERVAL_SECONDS = RATE_WINDOW_SECONDS / MAX_REQUESTS_PER_WINDOW


class OpenF1Error(RuntimeError):
    """Erro de comunicação ou de contrato retornado pela OpenF1."""


class RequestRateLimiter:
    """Paces all OpenF1 requests and enforces a rolling per-process minute cap."""

    def __init__(
        self,
        *,
        max_requests: int = MAX_REQUESTS_PER_WINDOW,
        window_seconds: float = RATE_WINDOW_SECONDS,
        min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a limiter with a rolling window and gradual dispatch interval."""
        if max_requests <= 0 or window_seconds <= 0 or min_interval_seconds < 0:
            raise ValueError("rate limiter settings must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleep = sleeper
        self._lock = Lock()
        self._request_times: deque[float] = deque()
        self._next_request_at = 0.0

    def acquire(self, endpoint: str) -> tuple[float, int]:
        """Wait for a request slot and log rolling-minute usage."""
        total_wait = 0.0
        with self._lock:
            while True:
                now = self._clock()
                self._remove_expired(now)
                pacing_wait = max(0.0, self._next_request_at - now)
                window_wait = (
                    max(0.0, self._request_times[0] + self.window_seconds - now)
                    if len(self._request_times) >= self.max_requests
                    else 0.0
                )
                wait = max(pacing_wait, window_wait)
                if wait <= 0:
                    break
                total_wait += wait
                logger.info(
                    "OpenF1 rate limiter wait endpoint=/%s "
                    "requests_last_minute=%d wait_seconds=%.3f",
                    endpoint,
                    len(self._request_times),
                    wait,
                )
                self._sleep(wait)

            now = self._clock()
            self._remove_expired(now)
            self._request_times.append(now)
            self._next_request_at = now + self.min_interval_seconds
            count = len(self._request_times)
            logger.info(
                "OpenF1 request dispatched endpoint=/%s "
                "requests_last_minute=%d wait_seconds=%.3f",
                endpoint,
                count,
                total_wait,
            )
            return total_wait, count

    def defer(self, seconds: float) -> None:
        """Apply a server-provided cooldown to every client in this process."""
        if seconds <= 0:
            return
        with self._lock:
            self._next_request_at = max(self._next_request_at, self._clock() + seconds)

    def _remove_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._request_times and self._request_times[0] <= cutoff:
            self._request_times.popleft()


GLOBAL_RATE_LIMITER = RequestRateLimiter()


def _parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After as delta seconds or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _error_body(exc: HTTPError) -> str:
    """Lê uma parte limitada do corpo HTTP para diagnóstico operacional."""
    body = exc.read(ERROR_BODY_LOG_LIMIT + 1).decode("utf-8", errors="replace")
    if len(body) > ERROR_BODY_LOG_LIMIT:
        return f"{body[:ERROR_BODY_LOG_LIMIT]}… [truncated]"
    return body or "<empty>"


def _log_request_failure(
    *,
    endpoint: str,
    url: str,
    exc: Exception,
    attempt: int,
    status: int | None,
    response_body: str | None,
    retry_delay: float | None,
    retry_after_seconds: float | None = None,
) -> None:
    """Registra URL, resposta, exceção, próxima ação e stack trace."""
    cause = getattr(exc, "reason", None)
    cause_details = (
        f" cause_type={type(cause).__name__} cause_message={cause}"
        if isinstance(cause, BaseException)
        else ""
    )
    action = (
        f"retry_in_seconds={retry_delay:.3f}"
        if retry_delay is not None
        else "retry=exhausted_or_permanent"
    )
    retry_after = (
        f" retry_after_seconds={retry_after_seconds:.3f}"
        if retry_after_seconds is not None
        else ""
    )
    logger.warning(
        "OpenF1 request failure endpoint=/%s url=%s status_http=%s "
        "response_body=%r exception_type=%s exception_message=%s%s%s "
        "attempt=%d %s",
        endpoint,
        url,
        status if status is not None else "<none>",
        response_body if response_body is not None else "<none>",
        type(exc).__name__,
        str(exc),
        cause_details,
        retry_after,
        attempt + 1,
        action,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


class OpenF1Client:
    """Consulta endpoints JSON da OpenF1 com retries limitados."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        """Guarda a configuração e usa o limitador global por padrão."""
        self.settings = settings
        self.rate_limiter = rate_limiter or GLOBAL_RATE_LIMITER

    def get(
        self, endpoint: str, filters: Mapping[str, FilterValue] | None = None
    ) -> list[dict[str, object]]:
        """Retorna registros do endpoint ou lança erro para respostas inválidas."""
        if not endpoint.replace("_", "").isalnum():
            raise ValueError("endpoint inválido")
        query = "&".join(
            f"{quote(str(key), safe='')}={quote(str(value), safe=':,')}"
            for key, value in (filters or {}).items()
        )
        url = f"{self.settings.base_url.rstrip('/')}/{endpoint}"
        if query:
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "f1-data-pipeline/0.1",
                **(
                    {"Authorization": f"Bearer {self.settings.api_token}"}
                    if self.settings.api_token
                    else {}
                ),
            },
        )
        for attempt in range(self.settings.max_retries + 1):
            self.rate_limiter.acquire(endpoint)
            try:
                with urlopen(
                    request, timeout=self.settings.timeout_seconds
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, list) or any(
                    not isinstance(row, dict) for row in payload
                ):
                    raise OpenF1Error(
                        f"Resposta inválida em /{endpoint}: "
                        "esperada uma lista de objetos"
                    )
                return payload
            except HTTPError as exc:
                response_body = _error_body(exc)
                retry_delay: float | None = None
                retry_after_delay: float | None = None
                if exc.code in TRANSIENT_STATUS:
                    retry_after_delay = _parse_retry_after(
                        exc.headers.get("Retry-After")
                    )
                    if retry_after_delay is not None:
                        self.rate_limiter.defer(retry_after_delay)
                    if attempt < self.settings.max_retries:
                        retry_delay = (
                            retry_after_delay
                            if retry_after_delay is not None
                            else 0.5 * 2**attempt
                        )
                        if retry_after_delay is None:
                            retry_delay += random.uniform(
                                0, min(retry_delay * 0.2, 1.0)
                            )
                _log_request_failure(
                    endpoint=endpoint,
                    url=url,
                    exc=exc,
                    attempt=attempt,
                    status=exc.code,
                    response_body=response_body,
                    retry_delay=retry_delay,
                    retry_after_seconds=retry_after_delay,
                )
                if retry_delay is None:
                    raise OpenF1Error(
                        f"OpenF1 respondeu HTTP {exc.code} em /{endpoint}"
                    ) from exc
                if retry_after_delay is None:
                    time.sleep(retry_delay)
            except (URLError, TimeoutError, OSError) as exc:
                retry_delay = (
                    0.5 * 2**attempt if attempt < self.settings.max_retries else None
                )
                if retry_delay is not None:
                    retry_delay += random.uniform(0, min(retry_delay * 0.2, 1.0))
                _log_request_failure(
                    endpoint=endpoint,
                    url=url,
                    exc=exc,
                    attempt=attempt,
                    status=None,
                    response_body=None,
                    retry_delay=retry_delay,
                )
                if retry_delay is None:
                    raise OpenF1Error(f"Falha de rede em /{endpoint}: {exc}") from exc
                time.sleep(retry_delay)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OpenF1Error(f"Resposta JSON inválida em /{endpoint}") from exc
        raise AssertionError("loop de retries terminou sem resultado")
