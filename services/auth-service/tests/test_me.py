"""GET /me: who the cookie is. The gateway asks it before it opens Grafana to someone."""


def test_the_cookie_of_an_admin_says_who_and_that_it_is_an_admin(logged_in_as):
    answer = logged_in_as("user1", is_admin=True).get("/me")

    assert answer.status_code == 200
    assert answer.json() == {"username": "user1", "is_admin": True}


def test_without_a_cookie_it_is_nobody(admin_client):
    assert admin_client.get("/me").status_code == 401
