"""The compiled web page, which is what `npm run build` makes in web-client/dist.

It is an explicit list, like the one of the API, and not a server of files: the page at `/` and at
`/unit/<code>` (the code of a territory, a district or a municipality), and the files that the build
names inside `/assets`. A file of the folder that is not in the list is not published, and a name
cannot walk out of the folder.
"""

import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Everything comes from the same site and nothing else can run: no scripts of other sites, no eval,
# no plugins, no frames of other sites, no forms. The style attribute is the only thing allowed
# inline (deck.gl sets sizes with it), and never a script.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "worker-src 'self' blob:; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

# HEAD asks for the headers only: link checkers, caches and tunnels do it before the page.
READ = ["GET", "HEAD"]

# The code of a territory has 2 digits, the one of a district 4 and the one of a municipality 5.
UNIT_CODE = re.compile(r"[0-9]{2}|[0-9]{4}|[0-9]{5}")
# The name of a file of the build: letters, digits, dots, hyphens and underscores, and it does not
# start with a dot, up to 100 characters (a longer one makes the system refuse the name with an
# error, which would be a 500 and a traceback in the log for anybody who asks). It has no slash, so
# it cannot name a folder or walk up one.
ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


def web_router(web_dir: Path) -> APIRouter:
    router = APIRouter()
    index = web_dir / "index.html"
    assets = (web_dir / "assets").resolve()

    def page() -> FileResponse:
        # The names of the files that it loads change with each build: a copy of an old page would
        # ask for files that no longer exist.
        return FileResponse(
            index, media_type="text/html", headers={**SECURITY_HEADERS, "Cache-Control": "no-cache"}
        )

    @router.api_route("/", methods=READ, include_in_schema=False)
    def root() -> FileResponse:
        return page()

    @router.api_route("/unit/{code}", methods=READ, include_in_schema=False)
    def unit(code: str) -> FileResponse:
        if not UNIT_CODE.fullmatch(code):
            raise StarletteHTTPException(404, "Not Found")
        return page()

    @router.api_route("/assets/{name}", methods=READ, include_in_schema=False)
    def asset(name: str) -> FileResponse:
        file = assets / name if ASSET_NAME.fullmatch(name) else None
        # resolve() follows a link: a link to a file outside the folder is not served.
        if file is None or not file.is_file() or not file.resolve().is_relative_to(assets):
            raise StarletteHTTPException(404, "Not Found")
        # Their name has the hash of their content: a new build has other names.
        return FileResponse(
            file,
            headers={**SECURITY_HEADERS, "Cache-Control": "public, max-age=31536000, immutable"},
        )

    return router
