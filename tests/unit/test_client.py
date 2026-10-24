"""Testes do cliente HTTP sem chamadas de rede reais."""

import io
import json
import logging
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from f1.config import Settings
from f1.ingestion.client import OpenF1Client, OpenF1Error, RequestRateLimiter


def make_unthrottled_limiter() -> RequestRateLimiter:
    """Provide a fresh limiter without real delays for isolated tests."""
    return RequestRateLimiter(max_requests=100, min_interval_seconds=0)


class FakeResponse:
    """Context manager mínimo para simular uma resposta HTTP."""

    def __init__(self, payload: object) -> None:
        self.body = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_: object) -> None:
        self.body.close()

    def read(self) -> bytes:
        return self.body.read()


def test_get_encodes_comparison_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_open(request: object, timeout: float) -> FakeResponse:
        seen.append(request.full_url)  # type: ignore[attr-defined]
        assert timeout == 2
        return FakeResponse([{"session_key": 1}])

    monkeypatch.setattr("f1.ingestion.client.urlopen", fake_open)
    client = OpenF1Client(
        Settings(timeout_seconds=2), rate_limiter=make_unthrottled_limiter()
    )
    assert client.get("laps", {"lap_duration>=": 90}) == [{"session_key": 1}]
    assert "lap_duration%3E%3D=" in seen[0]


def test_authenticated_client_sets_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str | None] = []

    def fake_open(request: object, timeout: float) -> FakeResponse:
        seen.append(request.get_header("Authorization"))  # type: ignore[attr-defined]
        return FakeResponse([])

    monkeypatch.setattr("f1.ingestion.client.urlopen", fake_open)
    client = OpenF1Client(
        Settings(api_token="test-token"), rate_limiter=make_unthrottled_limiter()
    )

    assert client.get("drivers") == []
    assert seen == ["Bearer test-token"]


def test_starting_grid_uses_qualifying_session_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_open(request: object, timeout: float) -> FakeResponse:
        seen.append(request.full_url)  # type: ignore[attr-defined]
        return FakeResponse([])

    monkeypatch.setattr("f1.ingestion.client.urlopen", fake_open)
    OpenF1Client(Settings(), rate_limiter=make_unthrottled_limiter()).get(
        "starting_grid", {"session_key": 7783}
    )
    assert seen == ["https://api.openf1.org/v1/starting_grid?session_key=7783"]


def test_get_rejects_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "f1.ingestion.client.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"bad": 1}),
    )
    with pytest.raises(OpenF1Error, match="Resposta inválida"):
        OpenF1Client(Settings(), rate_limiter=make_unthrottled_limiter()).get("laps")


def test_get_reports_permanent_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = HTTPError("https://api.openf1.org/v1/laps", 404, "not found", {}, None)
    monkeypatch.setattr(
        "f1.ingestion.client.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(OpenF1Error, match="HTTP 404"):
        OpenF1Client(Settings(), rate_limiter=make_unthrottled_limiter()).get("laps")


def test_retry_warning_logs_http_error_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    url = "https://api.openf1.org/v1/drivers?session_key=7"
    headers = Message()
    headers["Retry-After"] = "60"
    error = HTTPError(
        url,
        429,
        "Too Many Requests",
        headers,
        io.BytesIO(b'{"detail":"rate limit"}'),
    )
    responses = iter((error, FakeResponse([])))
    sleeps: list[float] = []
    now = [0.0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RequestRateLimiter(
        max_requests=100,
        min_interval_seconds=0,
        clock=lambda: now[0],
        sleeper=fake_sleep,
    )

    def fake_open(*_args: object, **_kwargs: object) -> FakeResponse:
        result = next(responses)
        if isinstance(result, HTTPError):
            raise result
        return result

    monkeypatch.setattr("f1.ingestion.client.urlopen", fake_open)
    assert (
        OpenF1Client(Settings(max_retries=1), rate_limiter=limiter).get(
            "drivers", {"session_key": 7}
        )
        == []
    )
    assert sleeps == [60.0]
    assert "endpoint=/drivers" in caplog.text
    assert f"url={url}" in caplog.text
    assert "status_http=429" in caplog.text
    assert 'response_body=\'{"detail":"rate limit"}\'' in caplog.text
    assert "exception_type=HTTPError" in caplog.text
    assert "Too Many Requests" in caplog.text
    assert "retry_in_seconds=60.000" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text


def test_network_warning_logs_captured_exception_and_cause(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    error = URLError(TimeoutError("socket timed out"))
    monkeypatch.setattr(
        "f1.ingestion.client.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(OpenF1Error, match="Falha de rede"):
        OpenF1Client(
            Settings(max_retries=0), rate_limiter=make_unthrottled_limiter()
        ).get("stints", {"session_key": 7})
    assert "endpoint=/stints" in caplog.text
    assert "status_http=<none>" in caplog.text
    assert "response_body='<none>'" in caplog.text
    assert "exception_type=URLError" in caplog.text
    assert "cause_type=TimeoutError" in caplog.text
    assert "socket timed out" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text


def test_rate_limiter_enforces_rolling_window_and_reports_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    now = [0.0]
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RequestRateLimiter(
        max_requests=2,
        window_seconds=60,
        min_interval_seconds=0,
        clock=lambda: now[0],
        sleeper=fake_sleep,
    )
    assert limiter.acquire("meetings") == (0.0, 1)
    assert limiter.acquire("sessions") == (0.0, 2)
    assert limiter.acquire("drivers") == (60.0, 1)
    assert sleeps == [60.0]
    assert "requests_last_minute=2" in caplog.text
    assert "wait_seconds=60.000" in caplog.text
    assert "endpoint=/drivers" in caplog.text
