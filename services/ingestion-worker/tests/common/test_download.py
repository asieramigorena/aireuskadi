import httpx
import pytest
from ingestion_worker.common.download import url_exists


def client(status):
    """An HTTP client that answers every request with this status, with no network."""
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))


def test_an_address_that_answers_200_exists():
    assert url_exists("https://example.test/aire_eprtr.csv", client=client(200)) is True


def test_an_address_that_answers_404_does_not_exist_yet():
    assert url_exists("https://example.test/aire_eprtr.csv", client=client(404)) is False


def test_a_server_error_is_not_taken_for_a_missing_address():
    with pytest.raises(httpx.HTTPStatusError):
        url_exists("https://example.test/aire_eprtr.csv", client=client(500))
