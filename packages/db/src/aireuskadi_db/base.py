"""Declarative base. The data lives in the ``core`` schema, the accounts in ``auth``."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "core"
# The accounts of the site live apart from the data.
AUTH_SCHEMA = "auth"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
