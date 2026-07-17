"""FastAPI application entry point."""

from fastapi import FastAPI

from pms_platform.api.routes import episodes, health

app = FastAPI(title="PMS Decision Platform", version="0.1.0")
app.include_router(health.router)
app.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
