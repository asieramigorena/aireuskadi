"""The words of the admin pages in the three languages of the site, and how the language is chosen.

As in the map: English unless the browser asks for Basque or Spanish, and `?lang=eu|es|en` chooses
it (the map passes its own language in its link to /admin). "Grafana" is a name: not translated.
The Basque texts are PENDING REVIEW by a Basque speaker, like the ones of the map.
Translation by Claude
"""

from fastapi import Request

LANGUAGES = ("en", "es", "eu")

TEXTS = {
    "en": {
        "admin": "Administration",
        "accounts": "Accounts",
        "map": "Map",
        "log_out": "Log out",
        "username": "Username",
        "password": "Password",
        "log_in": "Log in",
        "wrong": "Wrong username or password.",
        "too_many": "Too many failed logins: try again later.",
        "email": "Email",
        "role": "Role",
        "action": "Action",
        "role_admin": "admin",
        "role_user": "user",
        "you": "(you)",
        "make_admin": "Make admin",
        "remove_admin": "Remove admin",
    },
    "es": {
        "admin": "Administración",
        "accounts": "Cuentas",
        "map": "Mapa",
        "log_out": "Cerrar sesión",
        "username": "Usuario",
        "password": "Contraseña",
        "log_in": "Entrar",
        "wrong": "Usuario o contraseña incorrectos.",
        "too_many": "Demasiados intentos fallidos: prueba más tarde.",
        "email": "Correo",
        "role": "Rol",
        "action": "Acción",
        "role_admin": "admin",
        "role_user": "usuario",
        "you": "(tú)",
        "make_admin": "Hacer admin",
        "remove_admin": "Quitar admin",
    },
    "eu": {
        "admin": "Administrazioa",
        "accounts": "Kontuak",
        "map": "Mapa",
        "log_out": "Irten",
        "username": "Erabiltzailea",
        "password": "Pasahitza",
        "log_in": "Sartu",
        "wrong": "Erabiltzailea edo pasahitza okerra da.",
        "too_many": "Huts egindako saiakera gehiegi: saiatu berriro geroago.",
        "email": "Posta elektronikoa",
        "role": "Rola",
        "action": "Ekintza",
        "role_admin": "admin",
        "role_user": "erabiltzailea",
        "you": "(zu)",
        "make_admin": "Admin egin",
        "remove_admin": "Admin kendu",
    },
}


def chosen_language(request: Request) -> str | None:
    """The language of `?lang=`, if it is one of the three; otherwise None."""
    lang = request.query_params.get("lang")
    if lang in LANGUAGES:
        return lang
    return None


def language(request: Request) -> str:
    """The chosen language, else the first of the three that the browser asks for, else English."""
    lang = chosen_language(request)
    if lang:
        return lang
    # "es-ES,es;q=0.9,en;q=0.8": the browser lists them in its order of preference.
    for part in request.headers.get("accept-language", "").split(","):
        code = part.split(";")[0].strip().lower().split("-")[0]
        if code in LANGUAGES:
            return code
    return "en"


def with_language(url: str, request: Request) -> str:
    """`url` with `?lang=` added if the language was chosen by hand, so that it is kept."""
    lang = chosen_language(request)
    if lang is None:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}lang={lang}"
