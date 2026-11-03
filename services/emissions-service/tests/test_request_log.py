"""One log record per request, with the fields that Loki and the dashboards filter on."""

import logging

ACCESS = "emissions_service.access"


def requests_logged(caplog):
    return [r for r in caplog.records if r.name == ACCESS]


def test_each_request_leaves_one_record_with_method_path_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/pollutants?year=2023")

    (record,) = requests_logged(caplog)
    assert record.getMessage() == "request"
    assert record.method == "GET"
    assert record.path == "/pollutants"  # the query string is not logged
    assert record.status == 200
    assert record.duration_ms >= 0


def test_a_request_that_ends_in_an_error_is_logged_with_its_status(client, caplog):
    with caplog.at_level(logging.INFO, logger=ACCESS):
        client.get("/no-such-path")

    (record,) = requests_logged(caplog)
    assert record.status == 404
