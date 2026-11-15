"""The HTML of the admin pages: plain forms, no JavaScript and nothing loaded from elsewhere.

Written like page() of the course example fastapi-google-login: the HTML is a text in Python. What
comes from the database goes through html.escape, so it cannot become HTML of the page.

They look like the map (web-client/styles/style.css): the same night sea behind, the same pale
panel for reading, the same round buttons and the same colours.
Style by Claude
"""

from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse

from auth_service.texts import TEXTS, language, with_language

# Only the page itself and its inline style; the forms can only be sent to this site, and no other
# site can show the page inside a frame.
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    # Security fix by Claude (audit 2026-11-15): the address of an admin page never goes to
    # another site.
    "Referrer-Policy": "no-referrer",
}

# The colours and sizes of the map, copied from web-client/styles/style.css.
STYLE = """
:root {
  --sea: #0d1e26;
  --sea-line: #1d3844;
  --ink: #14262d;
  --paper: #eef2f0;
  --paper-line: #c9d4d0;
  --text-on-sea: #dce8e6;
  --muted-on-sea: #8fa8a8;
  --muted-on-paper: #4a5f66;
  font-family: ui-sans-serif, "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
  color-scheme: dark;
}
body {
  margin: 0;
  padding: clamp(0.75rem, 2.2vw, 1.5rem);
  background: var(--sea);
  color: var(--text-on-sea);
}
.brand { margin: 0; font-size: 1rem; font-weight: 600; }
.brand a { color: var(--muted-on-sea); text-decoration: none; }
h1 {
  margin: 0.15rem 0 0.6rem;
  font-size: clamp(1.2rem, 1rem + 1.2vw, 1.7rem);
  font-weight: 650;
  line-height: 1.15;
}
nav { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0 0 1.25rem; }
nav form { margin: 0; }
nav a, nav button {
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--sea-line);
  border-radius: 999px;
  background: rgb(13 30 38 / 0.6);
  color: var(--text-on-sea);
  font: inherit;
  font-size: 0.9rem;
  text-decoration: none;
  cursor: pointer;
}
nav a:hover, nav button:hover { border-color: var(--muted-on-sea); }
main {
  box-sizing: border-box;
  max-width: 26rem;
  padding: 1.25rem 1.4rem;
  background: var(--paper);
  color: var(--ink);
  border-radius: 6px;
  box-shadow: 0 12px 40px rgb(0 0 0 / 0.45);
}
main.wide { max-width: 40rem; }
label { display: block; margin-top: 0.8rem; color: var(--muted-on-paper); font-size: 0.9rem; }
input {
  display: block;
  box-sizing: border-box;
  width: 100%;
  margin-top: 0.25rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--muted-on-paper);
  border-radius: 6px;
  background: #fff;
  color: var(--ink);
  font: inherit;
}
.primary {
  margin-top: 1.1rem;
  padding: 0.5rem 1.2rem;
  border: 1px solid var(--ink);
  border-radius: 999px;
  background: var(--ink);
  color: var(--paper);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}
.error { margin: 0 0 0.5rem; color: #8a1c2e; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th, td {
  padding: 0.45rem 0.3rem;
  border-bottom: 1px solid var(--paper-line);
  text-align: left;
  vertical-align: middle;
}
th { font-weight: 500; color: var(--muted-on-paper); }
td form { margin: 0; }
td button {
  padding: 0.3rem 0.8rem;
  border: 1px solid var(--paper-line);
  border-radius: 999px;
  background: transparent;
  color: var(--ink);
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}
td button:hover { background: #e0e8e5; }
.me { color: var(--muted-on-paper); }
:focus-visible { outline: 2px solid #ffd479; outline-offset: 2px; }
/* Yellow is not seen on the pale card: there the outline is the ink, as in the panel of the map. */
main :focus-visible { outline-color: var(--ink); }
/* A title that is read aloud but not shown. */
.hidden-title {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (pointer: coarse) {
  nav a, nav button, td button, .primary { min-height: 2.75rem; }
}
"""


def nav(request: Request, user) -> str:
    """The way around: back to the map always; Grafana and the accounts only for an admin; out
    only for someone who is in. Nobody sees a door that they cannot open."""
    words = TEXTS[language(request)]
    links = f'<a href="{with_language("/", request)}">{words["map"]}</a>'
    if user and user.is_admin:
        # Grafana is not translated: its link is the same in every language.
        links += '<a href="/grafana/">Grafana</a>'
        links += f'<a href="{with_language("/admin/users", request)}">{words["accounts"]}</a>'
    if user:
        links += (
            f'<form method="post" action="{with_language("/admin/logout", request)}">'
            f"<button>{words['log_out']}</button></form>"
        )
    return f"<nav>{links}</nav>"


def page(request: Request, title: str, body: str, user, wide: bool = False) -> HTMLResponse:
    html = (
        f'<!doctype html><html lang="{language(request)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>AirEuskadi: {title}</title><style>{STYLE}</style></head>"
        f'<body><p class="brand"><a href="{with_language("/", request)}">AirEuskadi</a></p>'
        f"<h1>{title}</h1>{nav(request, user)}"
        f"<main{' class="wide"' if wide else ''}>{body}</main></body></html>"
    )
    return HTMLResponse(html, headers=HEADERS)


def login_page(request: Request, problem: str | None, user) -> HTMLResponse:
    """The form; `problem` is the key of the text that says what went wrong ("wrong",
    "too_many"), or None."""
    words = TEXTS[language(request)]
    message = f'<p class="error">{words[problem]}</p>' if problem else ""
    return page(
        request,
        words["admin"],
        f"""{message}
<form method="post" action="{with_language("/admin/login", request)}">
  <label>{words["username"]} <input name="username" autocomplete="username" required></label>
  <label>{words["password"]}
    <input name="password" type="password" autocomplete="current-password" required></label>
  <button class="primary">{words["log_in"]}</button>
</form>""",
        user,
    )


def users_page(request: Request, users: list, me) -> HTMLResponse:
    """The accounts, with a button to make each one an admin or a normal account (not oneself:
    so there is always an admin)."""
    words = TEXTS[language(request)]
    rows = ""
    for user in users:
        if user.id == me.id:
            action = f'<span class="me">{words["you"]}</span>'
        else:
            new_value = "false" if user.is_admin else "true"
            label = words["remove_admin"] if user.is_admin else words["make_admin"]
            url = with_language(f"/admin/users/{user.id}/admin", request)
            action = (
                f'<form method="post" action="{url}">'
                f'<input type="hidden" name="is_admin" value="{new_value}">'
                f"<button>{label}</button></form>"
            )
        role = words["role_admin"] if user.is_admin else words["role_user"]
        rows += (
            f"<tr><td>{escape(user.username)}</td><td>{escape(user.email or '')}</td>"
            f"<td>{role}</td><td>{action}</td></tr>"
        )
    return page(
        request,
        words["accounts"],
        f"""<table>
<thead><tr><th>{words["username"]}</th><th>{words["email"]}</th><th>{words["role"]}</th>
<th><span class="hidden-title">{words["action"]}</span></th></tr></thead>
<tbody>{rows}</tbody></table>""",
        me,
        wide=True,
    )
