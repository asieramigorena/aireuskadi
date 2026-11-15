"""The command of the owner to manage the accounts: ``aireuskadi-admin``.

    aireuskadi-admin add <name>        asks the password twice and adds a normal account
    aireuskadi-admin promote <name>    makes it an admin (the first admin is made like this)
    aireuskadi-admin demote <name>     makes it a normal account again
    aireuskadi-admin delete <name>
    aireuskadi-admin list

It reads the database URL from DATABASE_URL (the owner of the database). It never prints a
password or a hash.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from aireuskadi_db.accounts import Accounts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="aireuskadi-admin", description="Manage the accounts.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "promote", "demote", "delete"):
        commands.add_parser(name).add_argument("username")
    commands.add_parser("list")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set")
    engine = create_engine(url)
    accounts = Accounts(sessionmaker(engine, expire_on_commit=False))

    try:
        engine.connect().close()
    except OperationalError:
        # Not the error itself: it can carry the address of the database.
        sys.exit("Cannot connect to the database (DATABASE_URL)")

    try:
        if args.command == "list":
            for user in accounts.all():
                print(f"{user.username}\t{'admin' if user.is_admin else 'user'}")
        elif args.command == "add":
            password = getpass.getpass("Password: ")
            if getpass.getpass("Password again: ") != password:
                sys.exit("The passwords do not match")
            try:
                user = accounts.add(args.username, password)
            except ValueError as error:
                sys.exit(str(error))
            print(f"Account {user.username} added")
        else:
            user = accounts.find_by_name(args.username)
            if not user:
                sys.exit(f"There is no account called {args.username}")
            if args.command == "delete":
                accounts.delete(user.id)
                print(f"Account {user.username} deleted")
            else:
                is_admin = args.command == "promote"
                accounts.set_admin(user.id, is_admin)
                print(
                    f"Account {user.username} is now {'an admin' if is_admin else 'a normal account'}"
                )
    finally:
        engine.dispose()
