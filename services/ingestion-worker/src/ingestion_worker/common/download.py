"""HTTP download shared by the loaders. Tests replace it with a function that returns bytes."""

import httpx


def download(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.content


def url_exists(url: str, client: httpx.Client | None = None) -> bool:
    """Whether the address answers 200 (True) or 404 (False). Any other answer is an error: a
    server that is down must not look like a file that has not been published."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=60)
    try:
        response = client.head(url)
    finally:
        if own:
            client.close()
    if response.status_code == 404:
        return False
    response.raise_for_status()
    return True
