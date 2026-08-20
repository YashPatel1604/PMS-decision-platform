"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://pms:pms@localhost:5433/pms"
    raw_data_dir: Path = Path("./data/raw")
    external_data_dir: Path = Path("./data/external")
    export_dir: Path = Path("./data/exports")
    upload_dir: Path = Path("./data/uploads")
    final_master_dir: Path | None = None
    # Sibling OneDrive knowledge base: …/OneDrive-Personal/Research (read-only).
    research_dir: Path | None = None
    # Optional fallback dir of Portfolio_*.xlsx (Docker ships docker/portfolio_snapshot_seed).
    snapshot_seed_dir: Path | None = None
    yahoo_finance_base_url: str = "https://query1.finance.yahoo.com"
    fundamentals_provider: str = "manual"
    log_level: str = "INFO"

    # Auth (invite-only). Production VM: AUTH_DISABLED=0 + strong AUTH_SECRET.
    # Local solo Docker may set AUTH_DISABLED=1 until users exist.
    auth_disabled: bool = False
    auth_secret: str = ""
    auth_session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    auth_cookie_secure: bool = False
    # Comma-separated extra CORS origins (Tailscale UI URL, etc.)
    cors_origins: str = ""


settings = Settings()
