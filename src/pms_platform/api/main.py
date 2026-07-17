"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pms_platform.api.routes import dashboard, episodes, health

app = FastAPI(title="PMS Decision Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
