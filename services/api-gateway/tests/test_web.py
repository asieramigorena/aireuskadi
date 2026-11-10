"""The compiled web page: what the gateway serves from the folder that `npm run build` makes.

It is an explicit list, like the one of the API: the page at `/` and at `/unit/<code>`, and the
files that the build names inside `/assets`. A file of the folder that is not in the list is not
published, and a name cannot walk out of the folder.
"""

import httpx
import pytest
from api_gateway.main import create_app
from conftest import INDEX
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/", "/unit/01036", "/unit/9901", "/unit/48"])
def test_the_page_is_served_at_the_root_and_at_each_unit(web_client, path):
    response = web_client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX


def test_the_page_is_always_asked_for_again_before_it_is_used(web_client):
    # The names of the files that it loads change with each build: a copy of an old page would
    # ask for files that no longer exist.
    assert web_client.get("/").headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "path",
    [
        "/unit/abc",
        "/unit/1",
        "/unit/123",
        "/unit/123456",
        "/unit/%2e%2e",  # `..` itself is shortened to `/` by the client before it is sent
        "/unit/01036/extra",
        "/unit/",
        "/unit",
        "/units/01036",
        "/index.html",
        "/other",
    ],
)
def test_any_other_path_of_the_page_is_a_404_and_not_the_page(web_client, path):
    response = web_client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert INDEX not in response.text


@pytest.mark.parametrize(
    ("name", "content_type", "body"),
    [
        ("index-abc123.js", "javascript", "console.log(1);"),
        ("index-abc123.css", "text/css", "body{margin:0}"),
    ],
)
def test_the_files_of_the_build_are_served_and_kept_for_a_year(
    web_client, name, content_type, body
):
    # Their name has the hash of their content: a new build has other names.
    response = web_client.get(f"/assets/{name}")

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.text == body
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    "path",
    [
        "/assets/missing.js",
        "/assets/",
        "/assets",
        "/assets/.hidden",  # it exists in the folder, but no build names a file like that
        "/assets/../secret.txt",
        "/assets/%2e%2e/secret.txt",
        "/assets/..%2Fsecret.txt",
        "/assets/..%2F..%2Foutside.txt",
        "/assets/%2e%2e%2foutside.txt",
        "/assets/index-abc123.js/",
        "/assets/sub/index-abc123.js",
        "/assets/index-abc123.js%00.txt",
        "/assets/%5Cwindows",
        "/assets/" + "a" * 300,  # longer than a file name can be: the system refuses it, not us
        "/assets/" + "a" * 5000,
        "/secret.txt",
        "/outside.txt",
    ],
)
def test_nothing_else_is_published_and_no_name_walks_out_of_the_folder(web_client, path):
    response = web_client.get(path, follow_redirects=False)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    for private in ("in the folder", "outside the folder", "not an asset"):
        assert private not in response.text


@pytest.mark.parametrize("path", ["/", "/unit/01036", "/assets/index-abc123.js"])
def test_the_answers_come_with_the_headers_that_close_the_page(web_client, path):
    headers = web_client.get(path).headers

    csp = headers["content-security-policy"]
    # Everything comes from the same site, and nothing else can run: no scripts of other sites, no
    # eval, no plugins, no frames of other sites, no forms.
    for rule in (
        "default-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'none'",
    ):
        assert rule in csp, rule
    assert "unsafe-eval" not in csp
    # The only thing that is allowed inline is the style attribute (deck.gl sets sizes with it),
    # never a script.
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize("path", ["/", "/unit/01036", "/assets/index-abc123.js"])
def test_the_page_is_only_read(web_client, method, path):
    response = getattr(web_client, method)(path)

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"


def test_the_api_and_the_check_of_the_gateway_work_the_same_with_the_page(web_client, emissions):
    emissions.respond(body=b'{"answer": 42}')

    assert web_client.get("/api/v1/pollutants").json() == {"answer": 42}
    assert web_client.get("/health").json() == {"status": "ok"}
    assert web_client.get("/api/v1/health").status_code == 404
    assert web_client.get("/api/v1/unit/01036").status_code == 404
    assert web_client.get("/docs").status_code == 404


def test_the_pages_are_not_in_the_openapi_document_of_the_gateway(emissions, web_dir):
    upstream = httpx.AsyncClient(
        base_url="http://emissions.internal:8000", transport=httpx.MockTransport(emissions)
    )
    with TestClient(create_app(upstream, docs=True, web_dir=web_dir)) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert not any(p == "/" or p.startswith(("/unit", "/assets")) for p in paths)


@pytest.mark.parametrize("path", ["/", "/unit/01036", "/assets/index-abc123.js"])
def test_without_a_folder_there_is_no_page(client, path):
    # In development the page comes from Vite, and the gateway publishes only the API.
    assert client.get(path).status_code == 404


def test_a_file_of_the_folder_that_is_a_link_to_somewhere_else_is_not_served(web_client, web_dir):
    (web_dir / "assets" / "link.txt").symlink_to(web_dir.parent / "outside.txt")

    response = web_client.get("/assets/link.txt")

    assert response.status_code == 404
    assert "outside the folder" not in response.text


@pytest.mark.parametrize(
    ("path", "cache_control"),
    [
        ("/", "no-cache"),
        ("/unit/01036", "no-cache"),
        ("/assets/index-abc123.js", "public, max-age=31536000, immutable"),
    ],
)
def test_a_head_request_gets_the_headers_and_no_body(web_client, path, cache_control):
    # Link checkers, caches and tunnels ask this way before they ask for the page.
    response = web_client.head(path)

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["cache-control"] == cache_control
    assert "content-security-policy" in response.headers


def test_a_head_request_of_something_that_is_not_there_is_a_404(web_client):
    assert web_client.head("/assets/missing.js").status_code == 404
    assert web_client.head("/unit/abc").status_code == 404
