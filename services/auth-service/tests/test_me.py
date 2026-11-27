"""GET /me: who the cookie is. The gateway asks it before it opens Grafana to someone."""


def test_the_cookie_of_an_admin_says_who_and_that_it_is_an_admin(logged_in_as):
    answer = logged_in_as("user1", is_admin=True).get("/me")

    assert answer.status_code == 200
    assert answer.json() == {"username": "user1", "is_admin": True}


def test_without_a_cookie_it_is_nobody(admin_client):
    assert admin_client.get("/me").status_code == 401


def test_user_me_says_only_the_name_and_the_same_401_for_any_bad_cookie(logged_in_as, admin_client):
    # /user/me is for the page of the map: it says whether someone is logged in, and who.
    assert logged_in_as("user1", is_admin=True).get("/user/me").json() == {"username": "user1"}

    admin_client.cookies.set("__Host-aireuskadi_session", "forged")
    forged = admin_client.get("/user/me")
    admin_client.cookies.clear()
    missing = admin_client.get("/user/me")

    assert forged.status_code == missing.status_code == 401
    assert forged.text == missing.text
