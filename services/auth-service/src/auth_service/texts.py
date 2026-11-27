"""The words of the admin pages in the three languages of the site, and how the language is chosen.

As in the map: Basque (the site is .eus) unless `?lang=eu|es|en` chooses another; the map passes its
own language in its links to /user. "Grafana" is a name: not translated.
The Basque texts are PENDING REVIEW by a Basque speaker, like the ones of the map.
Translation by Claude
"""

from fastapi import Request

LANGUAGES = ("en", "es", "eu")

TEXTS = {
    "en": {
        "account": "Your account",
        "logged_in_as": "You are logged in as",
        "account_uses": "With it you can ask a language model about a municipality, from its panel on the map, with your own key.",
        "account_admin": "With it you can ask a language model about a municipality from the map, and see the accounts and Grafana in your panel.",
        "sign_up": "Sign up",
        "no_account": "No account? Sign up",
        "have_account": "Already have an account? Log in",
        "password_again": "Password again",
        "signup_rules": "3 to 40 lower case letters, digits, '_', '.' or '-'; a password of at least 5 characters.",
        "signup_refused": "This account could not be created: try another name or a longer password.",
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
        "account": "Tu cuenta",
        "logged_in_as": "Has iniciado sesión como",
        "account_uses": "Con ella puedes preguntar a un modelo de lenguaje sobre un municipio, desde su panel en el mapa, con tu propia clave.",
        "account_admin": "Con ella puedes preguntar a un modelo de lenguaje sobre un municipio desde el mapa, y ver las cuentas y Grafana en tu panel.",
        "sign_up": "Crear cuenta",
        "no_account": "¿No tienes cuenta? Crea una",
        "have_account": "¿Ya tienes cuenta? Entra",
        "password_again": "Repite la contraseña",
        "signup_rules": "De 3 a 40 minúsculas, números, '_', '.' o '-'; una contraseña de al menos 5 caracteres.",
        "signup_refused": "No se ha podido crear la cuenta: prueba otro nombre o una contraseña más larga.",
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
        "account": "Zure kontua",
        "logged_in_as": "Saioa hasi duzu honela:",
        "account_uses": "Horrekin hizkuntza-eredu bati galdetu diezaiokezu udalerri bati buruz, mapako bere paneletik, zure gakoarekin.",
        "account_admin": "Horrekin hizkuntza-eredu bati galdetu diezaiokezu udalerri bati buruz mapatik, eta kontuak eta Grafana ikusi zure panelean.",
        "sign_up": "Kontua sortu",
        "no_account": "Ez duzu konturik? Sortu bat",
        "have_account": "Baduzu kontua? Sartu",
        "password_again": "Errepikatu pasahitza",
        "signup_rules": "3 eta 40 artean letra xehe, zenbaki, '_', '.' edo '-'; gutxienez 5 karaktereko pasahitza.",
        "signup_refused": "Ezin izan da kontua sortu: saiatu beste izen batekin edo pasahitz luzeago batekin.",
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
    """The chosen language, else Basque."""
    return chosen_language(request) or "eu"


def with_language(url: str, request: Request) -> str:
    """`url` with `?lang=` added if the language was chosen by hand, so that it is kept."""
    lang = chosen_language(request)
    if lang is None:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}lang={lang}"
