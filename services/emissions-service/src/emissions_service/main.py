"""Emissions REST API entry point. Routes go here; the database is read-only."""

from fastapi import FastAPI

app = FastAPI(title="AirEuskadi Emissions Service")
