import httpx
import pytest
from ingestion_worker.common.download import download, url_exists


def client(status):
    """An HTTP client that answers every request with this status, with no network."""
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))


def test_an_address_that_answers_200_exists():
    assert url_exists("https://example.test/aire_eprtr.csv", client=client(200)) is True


def test_an_address_that_answers_404_does_not_exist_yet():
    assert url_exists("https://example.test/aire_eprtr.csv", client=client(404)) is False


def test_a_server_error_is_not_taken_for_a_missing_address():
    with pytest.raises(httpx.HTTPStatusError):
        url_exists(
            "https://example.test/aire_eprtr.csv", client=client(500), sleep=lambda seconds: None
        )


def answers(*statuses):
    """A client that answers each request with the next status (None: the network is cut), and
    the list of waits."""
    left = list(statuses)

    def answer(request):
        status = left.pop(0)
        if status is None:
            raise httpx.ConnectError("cut", request=request)
        return httpx.Response(status, content=b"data")

    return httpx.Client(transport=httpx.MockTransport(answer)), []


def test_a_download_is_tried_again_after_a_server_error_or_a_cut_but_not_after_a_404():
    # A 502 or a cut of the network is often over in seconds: without a retry the run would fail.
    client, waits = answers(502, None, 200)
    assert download("https://example.test/a", client=client, sleep=waits.append) == b"data"
    assert waits == [10, 10]

    # Asking again does not change a 404: it fails at once.
    client, waits = answers(404)
    with pytest.raises(httpx.HTTPStatusError):
        download("https://example.test/a", client=client, sleep=waits.append)
    assert waits == []
