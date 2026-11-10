"""Declarative base. Every table lives in the ``core`` schema."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

SCHEMA = "core"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)
