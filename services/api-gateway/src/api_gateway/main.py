"""Gateway entry point. Routes, composition and the Redis cache go here."""

from fastapi import FastAPI

app = FastAPI(title="AirEuskadi API Gateway")
