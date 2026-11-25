"""HTTP download shared by the loaders. Tests replace it with a function that returns bytes."""

import time

import httpx

ATTEMPTS = 3
WAIT_SECONDS = 10


def _new_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=60)


def _send(request, sleep) -> httpx.Response:
    """Calls request() up to 3 times. A network failure, a 429 or a 5xx of the source is often
    over in seconds; any other answer (a 404) would be the same again, so it is not repeated."""
    for _ in range(ATTEMPTS - 1):
        try:
            response = request()
            if response.status_code != 429 and response.status_code < 500:
                return response
        except httpx.TransportError:
            pass
        sleep(WAIT_SECONDS)
    return request()  # the last attempt: whatever it gives, or raises, goes on


def _ask(method: str, url: str, client: httpx.Client | None, sleep) -> httpx.Response:
    """Sends the request with the client given, or with one of its own that it closes after."""
    http = client or _new_client()
    try:
        return _send(lambda: http.request(method, url), sleep)
    finally:
        if client is None:
            http.close()


def download(url: str, client: httpx.Client | None = None, sleep=time.sleep) -> bytes:
    response = _ask("GET", url, client, sleep)
    response.raise_for_status()
    return response.content


def url_exists(url: str, client: httpx.Client | None = None, sleep=time.sleep) -> bool:
    """Whether the address answers 200 (True) or 404 (False). Any other answer is an error: a
    server that is down must not look like a file that has not been published."""
    response = _ask("HEAD", url, client, sleep)
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True
