"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://pms:pms@localhost:5433/pms"
    raw_data_dir: Path = Path("./data/raw")
    processed_data_dir: Path = Path("./data/processed")
    external_data_dir: Path = Path("./data/external")
    export_dir: Path = Path("./data/exports")
    upload_dir: Path = Path("./data/uploads")
    final_master_dir: Path | None = None
    # Sibling OneDrive knowledge base: …/OneDrive-Personal/Research (read-only).
    research_dir: Path | None = None
    yahoo_finance_base_url: str = "https://query1.finance.yahoo.com"
    log_level: str = "INFO"


settings = Settings()
