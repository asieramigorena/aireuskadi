"""/grafana/: the gateway asks the auth service who the cookie is, and passes the requests of an
admin to Grafana saying who the admin is.

Grafana trusts the header X-WEBAUTH-USER, so it must always be the one the gateway sets, never one
that came from the browser. Grafana and the auth service are fakes here (FakeUpstream).
"""

import httpx


def test_someone_who_is_not_an_admin_is_sent_to_the_login(admin_client, auth, grafana):
    auth.respond(body=b'{"username": "user2", "is_admin": false}')

    answer = admin_client.get("/grafana/d/abc", follow_redirects=False)

    assert (answer.status_code, answer.headers["location"]) == (303, "/admin")
    assert grafana.requests == []


def test_without_a_cookie_nobody_is_asked(admin_client, auth, grafana):
    admin_client.cookies.clear()

    answer = admin_client.get("/grafana/", follow_redirects=False)

    assert answer.status_code == 303
    assert auth.requests == [] and grafana.requests == []


def test_the_auth_service_is_asked_with_our_cookie_only(admin_client, auth):
    admin_client.cookies.set("grafana_session", "g1")

    admin_client.get("/grafana/")

    assert auth.requests[0].url.path == "/me"
    assert auth.requests[0].headers["cookie"] == "aireuskadi_session=the-jwt"


def test_grafana_gets_our_user_and_nothing_the_browser_could_forge(admin_client, grafana):
    admin_client.cookies.set("grafana_session", "g1")

    answer = admin_client.post(
        "/grafana/api/ds/query?from=now-1h",
        content=b'{"queries": []}',
        headers={
            "Content-Type": "application/json",
            "X-WEBAUTH-USER": "intruder",
            "X-WEBAUTH-ROLE": "Admin",
            "X-Forwarded-For": "10.0.0.1",
        },
    )

    sent = grafana.requests[0]
    assert answer.status_code == 200
    assert sent.method == "POST"
    assert sent.url.path == "/grafana/api/ds/query"
    assert sent.url.params["from"] == "now-1h"
    assert sent.content == b'{"queries": []}'
    assert sent.headers.get_list("x-webauth-user") == ["user1"]
    assert "x-webauth-role" not in sent.headers
    assert "x-forwarded-for" not in sent.headers
    # The cookies of Grafana go on; our JWT never leaves the gateway.
    assert sent.headers["cookie"] == "grafana_session=g1"


def test_the_answer_of_grafana_comes_back_with_its_status_and_cookies(admin_client, grafana):
    grafana.respond(
        302,
        b"",
        headers={"location": "/grafana/d/abc", "set-cookie": "grafana_session=g2; Path=/"},
    )

    answer = admin_client.get("/grafana/", follow_redirects=False)

    assert answer.status_code == 302
    assert answer.headers["location"] == "/grafana/d/abc"
    assert answer.headers["set-cookie"] == "grafana_session=g2; Path=/"


def test_a_path_with_dots_is_refused(admin_client, grafana):
    answer = admin_client.get("/grafana/%2e%2e/api/admin/users")

    assert answer.status_code == 404
    assert grafana.requests == []


def test_grafana_down_is_a_fixed_502(admin_client, grafana):
    grafana.error = httpx.ConnectError("refused")

    answer = admin_client.get("/grafana/")

    assert answer.status_code == 502
    assert "refused" not in answer.text


def test_a_strange_answer_of_the_auth_service_is_not_an_admin(admin_client, auth, grafana):
    auth.respond(body=b"not json")

    answer = admin_client.get("/grafana/", follow_redirects=False)

    assert answer.status_code == 303
    assert grafana.requests == []


def test_grafana_cannot_set_our_cookie(admin_client, grafana):
    # A browser trims the spaces around the name: this one would replace ours too.
    grafana.respond(headers={"set-cookie": "aireuskadi_session =from-grafana; Path=/"})

    answer = admin_client.get("/grafana/")

    assert "aireuskadi_session" not in answer.headers.get("set-cookie", "")
