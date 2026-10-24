"""Tables of the core schema.

Emissions (kg or t per year, declared by facilities or estimated by the regional
inventory) and concentrations (µg/m3, measured by stations) are kept separate.
Geometries use WGS 84 (EPSG:4326).
"""

from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aireuskadi_db.base import Base

SRID = 4326


# Administrative units: territory (province) > district (comarca) > municipality.


class Territory(Base):
    __tablename__ = "territory"

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True, comment="INE province code")
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=SRID))

    districts: Mapped[list["District"]] = relationship(back_populates="territory")


class District(Base):
    __tablename__ = "district"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    territory_code: Mapped[str] = mapped_column(ForeignKey("territory.code"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=SRID))

    territory: Mapped[Territory] = relationship(back_populates="districts")
    municipalities: Mapped[list["Municipality"]] = relationship(back_populates="district")


class Municipality(Base):
    __tablename__ = "municipality"

    ine_code: Mapped[str] = mapped_column(
        CHAR(5), primary_key=True, comment="INE municipality code"
    )
    district_code: Mapped[str] = mapped_column(ForeignKey("district.code"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    area_km2: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=SRID))

    district: Mapped[District] = relationship(back_populates="municipalities")
    facilities: Mapped[list["Facility"]] = relationship(back_populates="municipality")
    stations: Mapped[list["Station"]] = relationship(back_populates="municipality")


# Reference data.


class Pollutant(Base):
    __tablename__ = "pollutant"

    code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="NOX, NO2, PM10...")
    name: Mapped[str] = mapped_column(String(100))
    group: Mapped[str | None] = mapped_column(String(50))


class WhoGuideline(Base):
    """WHO air quality guideline value for a pollutant and averaging period."""

    __tablename__ = "who_guideline"

    pollutant_code: Mapped[str] = mapped_column(ForeignKey("pollutant.code"), primary_key=True)
    averaging_period: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="annual, 24h, 8h, 1h..."
    )
    edition: Mapped[int] = mapped_column(SmallInteger, primary_key=True, comment="e.g. 2021")
    value_ugm3: Mapped[Decimal] = mapped_column(Numeric(10, 3))


class ActivitySector(Base):
    """What emits: road transport, industry, energy... (SNAP / NFR)."""

    __tablename__ = "activity_sector"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, comment="SNAP or NFR code")
    classification: Mapped[str] = mapped_column(String(10), comment="SNAP or NFR")
    name: Mapped[str] = mapped_column(String(200))


# Emissions (mass per year).


class Facility(Base):
    """Industrial facility reporting to PRTR-Spain."""

    __tablename__ = "facility"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_code: Mapped[str] = mapped_column(ForeignKey("municipality.ine_code"), index=True)
    prtr_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    activity: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geometry("POINT", srid=SRID))

    municipality: Mapped[Municipality] = relationship(back_populates="facilities")
    emissions: Mapped[list["FacilityEmission"]] = relationship(back_populates="facility")


class FacilityEmission(Base):
    __tablename__ = "facility_emission"

    facility_id: Mapped[int] = mapped_column(ForeignKey("facility.id"), primary_key=True)
    pollutant_code: Mapped[str] = mapped_column(ForeignKey("pollutant.code"), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    amount_kg: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    method: Mapped[str | None] = mapped_column(
        String(1), comment="PRTR method: M measured, C calculated, E estimated"
    )

    facility: Mapped[Facility] = relationship(back_populates="emissions")
    pollutant: Mapped[Pollutant] = relationship()


class InventoryEmission(Base):
    """Region-wide (CAPV) inventory total per pollutant, sector and year."""

    __tablename__ = "inventory_emission"

    pollutant_code: Mapped[str] = mapped_column(ForeignKey("pollutant.code"), primary_key=True)
    activity_sector_id: Mapped[int] = mapped_column(
        ForeignKey("activity_sector.id"), primary_key=True
    )
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit: Mapped[str] = mapped_column(String(20), comment="as published, e.g. t or kt CO2-eq")

    pollutant: Mapped[Pollutant] = relationship()
    activity_sector: Mapped[ActivitySector] = relationship()


# Concentrations (µg/m3, measured).


class Station(Base):
    """Station of the Basque air quality network."""

    __tablename__ = "station"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    municipality_code: Mapped[str] = mapped_column(ForeignKey("municipality.ine_code"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    area_type: Mapped[str | None] = mapped_column(String(50), comment="urban, suburban, rural...")
    geom = mapped_column(Geometry("POINT", srid=SRID))

    municipality: Mapped[Municipality] = relationship(back_populates="stations")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="station")


class Measurement(Base):
    __tablename__ = "measurement"

    station_id: Mapped[int] = mapped_column(ForeignKey("station.id"), primary_key=True)
    pollutant_code: Mapped[str] = mapped_column(ForeignKey("pollutant.code"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, comment="UTC")
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(20), default="µg/m3")

    station: Mapped[Station] = relationship(back_populates="measurements")
    pollutant: Mapped[Pollutant] = relationship()
