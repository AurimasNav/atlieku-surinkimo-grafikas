"""HTTP downloads with retries: the public data sources occasionally return 5xx errors."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

USER_AGENT = (
    "atlieku-surinkimo-grafikas/0.1 (+https://github.com/AurimasNav/atlieku-surinkimo-grafikas)"
)
ATTEMPTS = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}


def get(url: str, timeout: float = 120, user_agent: str = USER_AGENT, sleep=time.sleep) -> bytes:
    """GET `url`, retrying server errors, rate limits and network failures with backoff
    (2, 4, 8, 16 s). Other HTTP errors, like 404, fail immediately."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUSES or attempt == ATTEMPTS:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == ATTEMPTS:
                raise
        sleep(2**attempt)
    raise AssertionError("unreachable")
