import io
import urllib.error

import pytest

from schedule_pipeline import http


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen(outcomes):
    """Returns a urlopen replacement that raises/returns the given outcomes in order."""
    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    return urlopen, calls


def http_error(code):
    return urllib.error.HTTPError("https://example.test", code, "error", {}, None)


def test_retries_server_errors_then_succeeds(monkeypatch):
    urlopen, calls = fake_urlopen([http_error(500), urllib.error.URLError("reset"), b"ok"])
    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    waits = []
    assert http.get("https://example.test", sleep=waits.append) == b"ok"
    assert len(calls) == 3
    assert waits == [2, 4]


def test_does_not_retry_client_errors(monkeypatch):
    urlopen, calls = fake_urlopen([http_error(404)])
    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        http.get("https://example.test", sleep=lambda _: None)
    assert len(calls) == 1


def test_gives_up_after_the_last_attempt(monkeypatch):
    urlopen, calls = fake_urlopen([http_error(503)] * http.ATTEMPTS)
    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        http.get("https://example.test", sleep=lambda _: None)
    assert len(calls) == http.ATTEMPTS
