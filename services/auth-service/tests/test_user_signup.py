"""/user/signup: anyone can make an account. It is never an admin, and a refusal never says why."""

PASSWORD = "a-long-password-1"


def sign_up(client, username, password, again=None, **extra):
    return client.post(
        "/user/signup",
        data={"username": username, "password": password, "again": again or password, **extra},
        follow_redirects=False,
    )


def test_a_sign_up_logs_in_and_goes_back_to_the_map_and_is_never_an_admin(
    admin_client, fake_accounts
):
    answer = sign_up(admin_client, "user1", PASSWORD, is_admin="on")

    assert answer.status_code == 303
    assert answer.headers["location"] == "/"
    assert "__Host-aireuskadi_session=" in answer.headers["set-cookie"]
    assert fake_accounts.find_by_name("user1").is_admin is False


def test_the_sign_up_page_is_a_form_in_the_language_of_the_page(admin_client):
    page = admin_client.get("/user/signup?lang=es").text

    assert '<form method="post" action="/user/signup?lang=es">' in page
    assert 'name="again"' in page


def test_every_refused_sign_up_is_the_same_answer(admin_client, fake_accounts):
    fake_accounts.add("user1", PASSWORD)

    refused = [
        sign_up(admin_client, "user1", PASSWORD),  # taken
        # the admin of Grafana, written with capitals and spaces
        sign_up(admin_client, " GrafanaAdmin ", PASSWORD),
        sign_up(admin_client, "user2", "abcd"),  # a short password
        sign_up(admin_client, "user3", PASSWORD, again="another-password-1"),  # typed twice wrong
        sign_up(admin_client, "a b", PASSWORD),  # a bad name
    ]

    assert {answer.status_code for answer in refused} == {400}
    assert len({answer.text for answer in refused}) == 1
    assert all("set-cookie" not in answer.headers for answer in refused)
    assert fake_accounts.find_by_name("grafanaadmin") is None


def test_a_sign_up_from_another_site_is_refused(admin_client, fake_accounts):
    answer = admin_client.post(
        "/user/signup",
        data={"username": "user1", "password": PASSWORD, "again": PASSWORD},
        headers={"Sec-Fetch-Site": "cross-site"},
    )

    assert answer.status_code == 403
    assert fake_accounts.find_by_name("user1") is None


def test_someone_logged_in_sees_the_way_out_on_the_sign_up_page(logged_in_as):
    page = logged_in_as("user1", is_admin=False).get("/user/signup").text

    assert 'action="/user/logout"' in page
