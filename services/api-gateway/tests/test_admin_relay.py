"""/admin/...: the gateway passes the admin pages on to the auth service and gives back its answer."""

import httpx


def test_the_page_of_the_auth_service_comes_back_as_it_is(admin_client, auth):
    auth.respond(
        200,
        b"<form>...</form>",
        "text/html",
        headers={"cache-control": "no-store", "date": "Mon, 01 Jan 2024 10:00:00 GMT"},
    )

    answer = admin_client.get("/admin")

    assert answer.status_code == 200
    assert answer.text == "<form>...</form>"
    assert answer.headers["cache-control"] == "no-store"
    # The server of the gateway writes its own date: the one of the service would be a second one.
    assert "01 Jan 2024" not in answer.headers.get("date", "")
    assert auth.requests[0].url.path == "/admin"


def test_the_login_form_goes_on_and_its_cookie_and_redirect_come_back(admin_client, auth):
    auth.respond(
        303, b"", headers={"location": "/grafana/", "set-cookie": "aireuskadi_session=new"}
    )
    admin_client.cookies.set("grafana_session", "g1")

    answer = admin_client.post(
        "/admin/login", data={"username": "user1", "password": "p"}, follow_redirects=False
    )

    sent = auth.requests[0]
    assert sent.method == "POST"
    assert sent.content == b"username=user1&password=p"
    # Only our cookie: the auth service has nothing to do with the session of Grafana.
    assert sent.headers["cookie"] == "aireuskadi_session=the-jwt"
    assert (answer.status_code, answer.headers["location"]) == (303, "/grafana/")
    assert answer.headers["set-cookie"] == "aireuskadi_session=new"


def test_the_auth_service_down_is_a_fixed_502(admin_client, auth):
    auth.error = httpx.ConnectError("refused")

    answer = admin_client.get("/admin")

    assert answer.status_code == 502
    assert "refused" not in answer.text


def test_without_the_auth_service_there_is_no_admin_page(client):
    assert client.get("/admin").status_code == 404


def test_a_path_with_dots_never_reaches_the_auth_service(admin_client, auth):
    # The client would turn /admin/../me into /me: an inside route of the auth service.
    answer = admin_client.get("/admin/%2e%2e/me")

    assert answer.status_code == 404
    assert auth.requests == []


def test_the_pages_of_everyone_under_user_go_to_the_auth_service_too(admin_client, auth):
    auth.respond(200, b"<form>login</form>", "text/html")

    assert admin_client.get("/user").text == "<form>login</form>"
    assert admin_client.get("/user/signup").status_code == 200
    assert [r.url.path for r in auth.requests] == ["/user", "/user/signup"]


def test_three_sign_ups_an_hour_per_person_then_429(admin_client, auth):
    # A script that makes accounts by the thousand, or that tries names to see which exist.
    auth.respond(303, b"", headers={"location": "/"})
    form = {"username": "user1", "password": "a-long-password-1", "again": "a-long-password-1"}

    statuses = [
        admin_client.post(
            "/user/signup",
            data=form,
            headers={"X-Forwarded-For": "203.0.113.7"},
            follow_redirects=False,
        ).status_code
        for _ in range(4)
    ]
    other = admin_client.post(
        "/user/signup",
        data=form,
        headers={"X-Forwarded-For": "198.51.100.1"},
        follow_redirects=False,
    )

    assert statuses == [303, 303, 303, 429]
    assert other.status_code == 303
    assert len(auth.requests) == 4


def test_the_auth_service_learns_who_the_person_is_from_the_gateway_only(admin_client, auth):
    # The lock of failed logins is per person and name: the person is what the tunnel says, never
    # a header that the browser chose.
    auth.respond(200, b"<form>login</form>", "text/html")

    admin_client.get("/user", headers={"X-Forwarded-For": "203.0.113.7", "X-Person": "someone"})

    assert auth.requests[0].headers["x-person"] == "203.0.113.7"
