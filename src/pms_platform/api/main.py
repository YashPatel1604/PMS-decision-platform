"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pms_platform.api.routes import (
    backtests,
    dashboard,
    episodes,
    health,
    holdings,
    imports,
    market_data,
    masters,
)

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
app.include_router(backtests.router, prefix="/backtests", tags=["backtests"])
app.include_router(holdings.router, prefix="/holdings", tags=["holdings"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
app.include_router(masters.router, prefix="/masters", tags=["masters"])
app.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
