"""The login of /user: the form, the JWT in a cookie, the limit of failures, the logout.

The accounts are a fake (FakeAccounts in conftest.py): these tests run without a database.
"""

import pytest

PASSWORD = "a-long-password-1"


def log_in(client, username, password, person="203.0.113.7"):
    # X-Person: who the person is, as the gateway says (the address that the tunnel gives).
    return client.post(
        "/user/login",
        data={"username": username, "password": password},
        headers={"X-Person": person},
        follow_redirects=False,
    )


def test_a_good_login_sets_the_cookie_and_goes_to_the_panel_or_to_the_map(
    admin_client, fake_accounts
):
    fake_accounts.add("user1", PASSWORD, is_admin=True)
    fake_accounts.add("user2", PASSWORD)

    answer = log_in(admin_client, "user1", PASSWORD)
    assert log_in(admin_client, "user2", PASSWORD).headers["location"] == "/"

    assert answer.status_code == 303
    assert answer.headers["location"] == "/admin"
    cookie = answer.headers["set-cookie"].lower()
    for flag in ("aireuskadi_session=", "httponly", "secure", "samesite=strict", "max-age=28800"):
        assert flag in cookie


def test_an_unknown_user_and_a_wrong_password_get_the_same_answer(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)

    unknown = log_in(admin_client, "nobody", "wrong-password-1")
    wrong = log_in(admin_client, "user1", "wrong-password-1")

    for answer in (unknown, wrong):
        assert answer.status_code == 303
        assert answer.headers["location"] == "/user?error=1"
        assert "set-cookie" not in answer.headers


def test_after_five_failures_even_the_right_password_is_refused(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)
    for _ in range(5):
        log_in(admin_client, "user1", "wrong-password-1")

    assert log_in(admin_client, "User1", PASSWORD).status_code == 429


def test_logout_deletes_the_cookie(admin_client):
    answer = admin_client.post("/user/logout", follow_redirects=False)

    assert answer.status_code == 303
    assert answer.headers["location"] == "/user"
    cookie = answer.headers["set-cookie"].lower()
    assert "max-age=0" in cookie
    # Deleted with the same flags it was set with: a browser could keep one set without them.
    assert "secure" in cookie and "samesite=strict" in cookie and "httponly" in cookie


def test_the_login_page_is_a_form_that_is_never_cached(admin_client):
    answer = admin_client.get("/user")

    assert answer.status_code == 200
    assert '<form method="post" action="/user/login">' in answer.text
    assert answer.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in answer.headers["content-security-policy"]


def test_no_password_or_token_reaches_the_log(admin_client, fake_accounts, caplog):
    fake_accounts.add("user1", PASSWORD)

    log_in(admin_client, "user1", PASSWORD)
    log_in(admin_client, "user1", "wrong-password-1")

    assert "a-long-password-1" not in caplog.text
    assert "wrong-password-1" not in caplog.text
    assert "eyJ" not in caplog.text  # the start of every JWT


def test_six_failures_of_an_unknown_name_are_a_429_like_the_ones_of_a_real_name(
    admin_client, fake_accounts
):
    # The lock must not tell which names exist: it counts every name, real or not.
    fake_accounts.add("user1", PASSWORD)
    for name in ("user1", "nobody"):
        for _ in range(5):
            log_in(admin_client, name, "wrong-password-1")

    real, unknown = log_in(admin_client, "user1", PASSWORD), log_in(admin_client, "nobody", "x")

    assert real.status_code == unknown.status_code == 429
    assert real.text == unknown.text


def test_the_memory_of_the_failures_never_holds_more_than_its_limit(admin_client, monkeypatch):
    # Names that are tried once and never again must not fill the memory: the oldest go first.
    monkeypatch.setattr("auth_service.session.MAX_NAMES", 3)
    for name in ("user1", "user2", "user3", "user4"):
        log_in(admin_client, name, "wrong-password-1")

    assert [name for _, name in admin_client.app.state.failures] == ["user2", "user3", "user4"]


def test_the_failures_of_one_person_do_not_lock_the_account_for_another(
    admin_client, fake_accounts
):
    # Otherwise anyone could keep an admin out by failing 5 times with their name.
    fake_accounts.add("user1", PASSWORD)
    for _ in range(5):
        log_in(admin_client, "user1", "wrong-password-1", person="198.51.100.9")

    assert log_in(admin_client, "user1", PASSWORD, person="198.51.100.9").status_code == 429
    assert log_in(admin_client, "user1", PASSWORD).status_code == 303


def test_without_a_session_the_page_offers_only_the_way_back_to_the_map(admin_client):
    page = admin_client.get("/user?lang=en").text

    assert ">Map</a>" in page
    assert "/grafana/" not in page
    assert 'href="/admin"' not in page
    assert "/user/logout" not in page
    assert 'href="/user/signup' in page


def test_an_admin_sees_the_way_to_grafana_the_panel_and_out(logged_in_as):
    page = logged_in_as("user1", is_admin=True).get("/user").text

    assert 'href="/grafana/"' in page
    assert 'href="/admin"' in page
    assert 'action="/user/logout"' in page


def test_someone_logged_in_sees_their_account_and_not_the_login_form(logged_in_as):
    page = logged_in_as("user2", is_admin=False).get("/user?lang=en").text

    assert "user2" in page
    assert 'action="/user/login"' not in page
    # Not an admin: only the map and the way out, never Grafana or the panel.
    assert ">Map</a>" in page and 'action="/user/logout' in page
    assert "/grafana/" not in page
    assert 'href="/admin"' not in page


# The language: Basque, like the map (the site is .eus), unless ?lang= chooses another.


@pytest.mark.parametrize("browser", ["fr-FR,fr", "es-ES,es;q=0.9,en;q=0.8", "en"])
def test_the_pages_are_in_basque_whatever_the_browser_asks_for(admin_client, browser):
    page = admin_client.get("/user", headers={"Accept-Language": browser}).text

    assert '<html lang="eu">' in page
    assert "Pasahitza" in page


def test_a_chosen_language_wins_and_stays_in_the_links_and_forms(logged_in_as):
    client = logged_in_as("user1", is_admin=True)

    page = client.get("/user?lang=es").text

    assert '<html lang="es">' in page
    assert 'action="/user/logout?lang=es"' in page
    assert 'href="/admin?lang=es"' in page
    # Grafana is not translated: the link goes to it as it is.
    assert 'href="/grafana/"' in page


def test_a_failed_login_comes_back_in_the_chosen_language(admin_client):
    answer = admin_client.post(
        "/user/login?lang=es",
        data={"username": "nobody", "password": "wrong-password-1"},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/user?error=1&lang=es"


def test_a_language_that_is_not_one_of_the_three_is_ignored(admin_client):
    page = admin_client.get('/admin?lang="><script>').text

    assert '<html lang="eu">' in page
    assert "<script>" not in page


# What the audits added: the page of the 429, the defences of the forms, the logout.


def test_too_many_failures_is_the_login_page_with_the_reason_in_its_language(
    admin_client, fake_accounts
):
    fake_accounts.add("user1", PASSWORD)
    for _ in range(5):
        log_in(admin_client, "user1", "wrong-password-1")

    answer = admin_client.post(
        "/user/login?lang=es",
        data={"username": "user1", "password": PASSWORD},
        headers={"X-Person": "203.0.113.7"},
        follow_redirects=False,
    )

    assert answer.status_code == 429
    assert "Demasiados intentos" in answer.text
    assert '<form method="post"' in answer.text


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_a_form_sent_from_another_site_is_refused(admin_client, fake_accounts, site):
    # same-site is another name under the same domain (anything.aireuskadi.eus): not this site.
    fake_accounts.add("user1", PASSWORD)
    from_elsewhere = {"Sec-Fetch-Site": site}

    login = admin_client.post(
        "/user/login",
        data={"username": "user1", "password": PASSWORD},
        headers=from_elsewhere,
        follow_redirects=False,
    )
    logout = admin_client.post("/user/logout", headers=from_elsewhere, follow_redirects=False)

    assert login.status_code == 403 and "set-cookie" not in login.headers
    assert logout.status_code == 403 and "set-cookie" not in logout.headers


@pytest.mark.parametrize("written", ["as it was", "with a = at the end"])
def test_after_the_logout_the_old_token_is_worth_nothing(admin_client, fake_accounts, written):
    # The JWT library also accepts the token with a "=" at the end: it is the same token.
    fake_accounts.add("user1", PASSWORD)
    token = log_in(admin_client, "user1", PASSWORD).cookies["aireuskadi_session"]

    admin_client.post("/user/logout")
    admin_client.cookies.set("aireuskadi_session", token if written == "as it was" else token + "=")

    assert admin_client.get("/me").status_code == 401


def test_the_redirects_are_not_kept_and_send_no_referrer(admin_client):
    answer = admin_client.post("/user/logout", follow_redirects=False)

    assert answer.headers["cache-control"] == "no-store"
    assert answer.headers["referrer-policy"] == "no-referrer"


def test_a_logout_with_a_token_that_is_not_ours_keeps_nothing_in_memory(admin_client):
    # Anyone can send a logout with any cookie: only real tokens are remembered.
    admin_client.cookies.set("aireuskadi_session", "x" * 5000)

    admin_client.post("/user/logout")

    assert admin_client.app.state.logged_out == set()


def test_the_pages_have_the_icon_of_the_map_in_the_tab(admin_client):
    # The same wind emoji as the map, so the tab keeps its icon on the login and the panel.
    answer = admin_client.get("/user")

    assert '<link rel="icon" href="data:image/svg+xml,' in answer.text
    assert "img-src data:" in answer.headers["content-security-policy"]
