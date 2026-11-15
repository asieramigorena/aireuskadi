"""The login of the admin page: the form, the JWT in a cookie, the limit of failures, the logout.

The accounts are a fake (FakeAccounts in conftest.py): these tests run without a database.
"""

PASSWORD = "a-long-password-1"


def log_in(client, username, password):
    return client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_a_good_login_sets_the_cookie_and_goes_to_grafana(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD, is_admin=True)

    answer = log_in(admin_client, "user1", PASSWORD)

    assert answer.status_code == 303
    assert answer.headers["location"] == "/grafana/"
    cookie = answer.headers["set-cookie"].lower()
    for flag in ("aireuskadi_session=", "httponly", "secure", "samesite=strict", "max-age=28800"):
        assert flag in cookie


def test_an_unknown_user_and_a_wrong_password_get_the_same_answer(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)

    unknown = log_in(admin_client, "nobody", "wrong-password-1")
    wrong = log_in(admin_client, "user1", "wrong-password-1")

    for answer in (unknown, wrong):
        assert answer.status_code == 303
        assert answer.headers["location"] == "/admin?error=1"
        assert "set-cookie" not in answer.headers


def test_after_five_failures_even_the_right_password_is_refused(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)
    for _ in range(5):
        log_in(admin_client, "user1", "wrong-password-1")

    assert log_in(admin_client, "User1", PASSWORD).status_code == 429


def test_logout_deletes_the_cookie(admin_client):
    answer = admin_client.post("/admin/logout", follow_redirects=False)

    assert answer.status_code == 303
    assert answer.headers["location"] == "/admin"
    assert "max-age=0" in answer.headers["set-cookie"].lower()


def test_the_login_page_is_a_form_that_is_never_cached(admin_client):
    answer = admin_client.get("/admin")

    assert answer.status_code == 200
    assert '<form method="post" action="/admin/login">' in answer.text
    assert answer.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in answer.headers["content-security-policy"]


def test_no_password_or_token_reaches_the_log(admin_client, fake_accounts, caplog):
    fake_accounts.add("user1", PASSWORD)

    log_in(admin_client, "user1", PASSWORD)
    log_in(admin_client, "user1", "wrong-password-1")

    assert "a-long-password-1" not in caplog.text
    assert "wrong-password-1" not in caplog.text
    assert "eyJ" not in caplog.text  # the start of every JWT


def test_only_the_failures_of_real_accounts_are_remembered(admin_client, fake_accounts):
    # Names that are tried once and never again (or are huge) must not fill the memory.
    fake_accounts.add("user1", PASSWORD)

    log_in(admin_client, "x" * 1000, "wrong-password-1")
    log_in(admin_client, "nobody", "wrong-password-1")
    log_in(admin_client, "user1", "wrong-password-1")

    assert list(admin_client.app.state.failures) == ["user1"]


def test_without_a_session_the_page_offers_only_the_way_back_to_the_map(admin_client):
    page = admin_client.get("/admin").text

    assert ">Map</a>" in page
    assert "/grafana/" not in page
    assert "/admin/users" not in page
    assert "/admin/logout" not in page


def test_an_admin_sees_the_way_to_grafana_the_accounts_and_out(logged_in_as):
    page = logged_in_as("user1", is_admin=True).get("/admin").text

    assert 'href="/grafana/"' in page
    assert 'href="/admin/users"' in page
    assert 'action="/admin/logout"' in page


def test_an_account_that_is_not_an_admin_sees_only_the_map_and_out(logged_in_as):
    page = logged_in_as("user2", is_admin=False).get("/admin").text

    assert ">Map</a>" in page
    assert "/grafana/" not in page
    assert "/admin/users" not in page
    assert 'action="/admin/logout"' in page


# The language: English unless the browser asks for Basque or Spanish, or ?lang= chooses it.


def test_the_pages_are_in_english_by_default(admin_client):
    page = admin_client.get("/admin", headers={"Accept-Language": "fr-FR,fr"}).text

    assert '<html lang="en">' in page
    assert "Password" in page and "Log in" in page


def test_the_language_of_the_browser_is_followed(admin_client):
    page = admin_client.get("/admin", headers={"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"}).text

    assert '<html lang="es">' in page
    assert "Contraseña" in page


def test_a_chosen_language_wins_and_stays_in_the_links_and_forms(logged_in_as):
    client = logged_in_as("user1", is_admin=True)

    page = client.get("/admin?lang=eu", headers={"Accept-Language": "es"}).text

    assert '<html lang="eu">' in page
    assert 'action="/admin/login?lang=eu"' in page
    assert 'href="/admin/users?lang=eu"' in page
    # Grafana is not translated: the link goes to it as it is.
    assert 'href="/grafana/"' in page


def test_a_failed_login_comes_back_in_the_chosen_language(admin_client):
    answer = admin_client.post(
        "/admin/login?lang=es",
        data={"username": "nobody", "password": "wrong-password-1"},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/admin?error=1&lang=es"


def test_a_language_that_is_not_one_of_the_three_is_ignored(admin_client):
    page = admin_client.get('/admin?lang="><script>').text

    assert '<html lang="en">' in page
    assert "<script>" not in page


# What the audits added: the page of the 429, the defences of the forms, the logout.


def test_too_many_failures_is_the_login_page_with_the_reason_in_its_language(
    admin_client, fake_accounts
):
    fake_accounts.add("user1", PASSWORD)
    for _ in range(5):
        log_in(admin_client, "user1", "wrong-password-1")

    answer = admin_client.post(
        "/admin/login?lang=es",
        data={"username": "user1", "password": PASSWORD},
        follow_redirects=False,
    )

    assert answer.status_code == 429
    assert "Demasiados intentos" in answer.text
    assert '<form method="post"' in answer.text


def test_a_form_sent_from_another_site_is_refused(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)
    from_elsewhere = {"Sec-Fetch-Site": "cross-site"}

    login = admin_client.post(
        "/admin/login",
        data={"username": "user1", "password": PASSWORD},
        headers=from_elsewhere,
        follow_redirects=False,
    )
    logout = admin_client.post("/admin/logout", headers=from_elsewhere, follow_redirects=False)

    assert login.status_code == 403 and "set-cookie" not in login.headers
    assert logout.status_code == 403 and "set-cookie" not in logout.headers


def test_after_the_logout_the_old_token_is_worth_nothing(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)
    token = log_in(admin_client, "user1", PASSWORD).cookies["aireuskadi_session"]

    admin_client.post("/admin/logout")
    admin_client.cookies.set("aireuskadi_session", token)

    assert admin_client.get("/me").status_code == 401


def test_the_redirects_are_not_kept_and_send_no_referrer(admin_client):
    answer = admin_client.post("/admin/logout", follow_redirects=False)

    assert answer.headers["cache-control"] == "no-store"
    assert answer.headers["referrer-policy"] == "no-referrer"


def test_an_unknown_name_costs_a_bcrypt_check_like_a_known_one(admin_client, monkeypatch):
    # Otherwise the answer comes faster for a name that does not exist, and says so.
    checks = []
    monkeypatch.setattr("auth_service.admin.verify_password", lambda *args: checks.append(1))

    log_in(admin_client, "nobody", "wrong-password-1")

    assert checks == [1]


def test_a_language_of_three_letters_is_not_taken_for_one_of_two(admin_client):
    page = admin_client.get("/admin", headers={"Accept-Language": "est"}).text

    assert '<html lang="en">' in page


def test_a_logout_with_a_token_that_is_not_ours_keeps_nothing_in_memory(admin_client):
    # Anyone can send a logout with any cookie: only real tokens are remembered.
    admin_client.cookies.set("aireuskadi_session", "x" * 5000)

    admin_client.post("/admin/logout")

    assert admin_client.app.state.logged_out == set()


def test_after_the_logout_the_same_token_written_another_way_is_worth_nothing(
    admin_client, fake_accounts
):
    # The JWT library also accepts the token with a "=" at the end: it is the same token.
    fake_accounts.add("user1", PASSWORD)
    token = log_in(admin_client, "user1", PASSWORD).cookies["aireuskadi_session"]

    admin_client.post("/admin/logout")
    admin_client.cookies.set("aireuskadi_session", token + "=")

    assert admin_client.get("/me").status_code == 401
