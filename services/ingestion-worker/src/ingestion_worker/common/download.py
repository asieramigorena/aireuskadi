"""HTTP download shared by the loaders. Tests replace it with a function that returns bytes."""

import httpx


def download(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.content
