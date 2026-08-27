"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pms_platform.api.auth_middleware import AuthMiddleware
from pms_platform.api.routes import (
    auth,
    backtests,
    change_requests,
    client_portfolio,
    charts,
    dashboard,
    episodes,
    health,
    holdings,
    imports,
    market_data,
    masters,
    pivot_strategy,
    staged_imports,
    watchlists,
)
from pms_platform.config import settings

app = FastAPI(title="PMS Decision Platform", version="0.1.0")

_default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[*_default_origins, *_extra],
    # Tailscale mesh UIs: http://100.x.x.x:3000
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|100\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after CORS so it runs first on the request path; OPTIONS stays public.
app.add_middleware(AuthMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(change_requests.router)
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
app.include_router(backtests.router, prefix="/backtests", tags=["backtests"])
app.include_router(holdings.router, prefix="/holdings", tags=["holdings"])
app.include_router(imports.router, prefix="/imports", tags=["imports"])
app.include_router(staged_imports.router)
app.include_router(masters.router, prefix="/masters", tags=["masters"])
app.include_router(market_data.router, prefix="/market-data", tags=["market-data"])
app.include_router(pivot_strategy.router, prefix="/strategy/pivot", tags=["pivot-strategy"])
app.include_router(
    client_portfolio.router,
    prefix="/strategy/client-portfolio",
    tags=["client-portfolio"],
)
app.include_router(charts.router, prefix="/strategy/charts", tags=["charts"])
app.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
