"""/admin, the panel: only an admin sees the accounts and the way to Grafana, and promotes or demotes
the others. For anyone else the panel does not exist (404); without a session, the login."""

from datetime import UTC, datetime, timedelta

import jwt
from auth_service.session import COOKIE, create_access_token

# The secret of the service in conftest.py. Not imported from it: there are several conftest.py
# in the repository and `import conftest` can find another one.
JWT_SECRET = "x" * 32


def test_an_admin_sees_the_accounts_with_what_they_hold_escaped(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=True)
    user2 = fake_accounts.add("user2", "a-long-password-1")
    user2.email = "<b>user2@example.org</b>"

    page = client.get("/admin")

    assert page.status_code == 200
    assert "user1" in page.text and "user2" in page.text
    assert 'href="/grafana/"' in page.text
    assert "&lt;b&gt;user2@example.org&lt;/b&gt;" in page.text


def test_an_admin_promotes_a_normal_account(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=True)
    user2 = fake_accounts.add("user2", "a-long-password-1")

    answer = client.post(
        f"/admin/users/{user2.id}/admin", data={"is_admin": "true"}, follow_redirects=False
    )

    assert answer.status_code == 303
    assert answer.headers["location"] == "/admin"
    assert fake_accounts.find(user2.id).is_admin is True


def test_for_a_normal_account_the_panel_does_not_exist(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=False)
    user1 = fake_accounts.find_by_name("user1")

    page = client.get("/admin", follow_redirects=False)
    change = client.post(
        f"/admin/users/{user1.id}/admin", data={"is_admin": "true"}, follow_redirects=False
    )

    assert page.status_code == change.status_code == 404
    assert fake_accounts.find(user1.id).is_admin is False


def test_an_admin_cannot_remove_their_own_admin(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=True)
    user1 = fake_accounts.find_by_name("user1")

    answer = client.post(f"/admin/users/{user1.id}/admin", data={"is_admin": "false"})

    assert answer.status_code == 400
    assert fake_accounts.find(user1.id).is_admin is True


def test_an_account_that_does_not_exist_is_a_404(logged_in_as):
    client = logged_in_as("user1", is_admin=True)

    assert client.post("/admin/users/999/admin", data={"is_admin": "true"}).status_code == 404


def is_sent_to_the_login(client):
    answer = client.get("/admin", follow_redirects=False)
    return answer.status_code == 303 and answer.headers["location"] == "/user"


def test_a_token_signed_with_another_secret_is_nobody(admin_client, fake_accounts):
    user1 = fake_accounts.add("user1", "a-long-password-1", is_admin=True)
    admin_client.cookies.set(COOKIE, create_access_token(user1.id, "y" * 32))

    assert is_sent_to_the_login(admin_client)


def test_an_expired_token_is_nobody(admin_client, fake_accounts):
    user1 = fake_accounts.add("user1", "a-long-password-1", is_admin=True)
    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    admin_client.cookies.set(
        COOKIE, jwt.encode({"sub": str(user1.id), "exp": an_hour_ago}, JWT_SECRET)
    )

    assert is_sent_to_the_login(admin_client)


def test_a_token_that_never_ends_is_nobody(admin_client, fake_accounts):
    user1 = fake_accounts.add("user1", "a-long-password-1", is_admin=True)
    admin_client.cookies.set(COOKIE, jwt.encode({"sub": str(user1.id)}, JWT_SECRET))

    assert is_sent_to_the_login(admin_client)


def test_a_deleted_or_demoted_account_loses_its_access_at_once(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=True)
    user1 = fake_accounts.find_by_name("user1")

    fake_accounts.set_admin(user1.id, False)
    assert client.get("/admin", follow_redirects=False).status_code == 404

    fake_accounts.delete(user1.id)
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_a_bad_form_from_someone_who_is_not_an_admin_is_sent_to_the_login_first(admin_client):
    # The check of who it is comes before the check of the form: a 422 would say the route exists.
    answer = admin_client.post(
        "/admin/users/1/admin", data={"is_admin": "maybe"}, follow_redirects=False
    )

    assert (answer.status_code, answer.headers["location"]) == (303, "/user")


def test_the_change_is_refused_from_another_site(logged_in_as, fake_accounts):
    client = logged_in_as("user1", is_admin=True)
    user2 = fake_accounts.add("user2", "a-long-password-1")

    answer = client.post(
        f"/admin/users/{user2.id}/admin",
        data={"is_admin": "true"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )

    assert answer.status_code == 403
    assert fake_accounts.find(user2.id).is_admin is False


def test_without_the_form_field_someone_who_is_not_an_admin_is_sent_to_the_login(admin_client):
    answer = admin_client.post("/admin/users/1/admin", follow_redirects=False)

    assert (answer.status_code, answer.headers["location"]) == (303, "/user")


def test_an_account_deleted_at_the_same_moment_is_a_404_and_not_a_change(
    logged_in_as, fake_accounts, monkeypatch
):
    client = logged_in_as("user1", is_admin=True)
    user2 = fake_accounts.add("user2", "a-long-password-1")
    monkeypatch.setattr(fake_accounts, "set_admin", lambda user_id, is_admin: False)

    answer = client.post(f"/admin/users/{user2.id}/admin", data={"is_admin": "true"})

    assert answer.status_code == 404
