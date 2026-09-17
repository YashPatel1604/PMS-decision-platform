"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://pms:pms@localhost:5433/pms"
    # Direct connection for controlled migrations (Supabase direct / non-pooler).
    database_direct_url: str | None = None
    raw_data_dir: Path = Path("./data/raw")
    external_data_dir: Path = Path("./data/external")
    export_dir: Path = Path("./data/exports")
    upload_dir: Path = Path("./data/uploads")
    private_storage_dir: Path = Path("./data/uploads/private")
    final_master_dir: Path | None = None
    # Sibling OneDrive knowledge base: …/OneDrive-Personal/Research (read-only).
    research_dir: Path | None = None
    # Writable DailyEditFiles (Charts + SCA_LLP). Not Research.
    daily_edit_dir: Path | None = None
    # Optional fallback dir of Portfolio_*.xlsx (Docker ships docker/portfolio_snapshot_seed).
    snapshot_seed_dir: Path | None = None
    yahoo_finance_base_url: str = "https://query1.finance.yahoo.com"
    fundamentals_provider: str = "manual"

    # Auth (invite-only). Production VM: AUTH_DISABLED=0 + strong AUTH_SECRET.
    # Local solo Docker may set AUTH_DISABLED=1 until users exist.
    auth_disabled: bool = False
    auth_secret: str = ""
    auth_session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days
    auth_cookie_secure: bool = False
    # Comma-separated extra CORS origins (Tailscale UI URL, etc.)
    cors_origins: str = ""

    # Centralization feature flags (defaults preserve current local behavior).
    feature_legacy_excel_read: bool = True
    feature_legacy_excel_write: bool = True
    feature_approval_workflow: bool = False
    feature_cloud_storage: bool = False

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "source-files"

    # Nightly local folder mirror (Mac Docker). Graph uses microsoft_* below.
    onedrive_backup_enabled: bool = False
    onedrive_backup_dir: Path | None = None
    onedrive_backup_hour_ist: int = 19
    # Microsoft Graph (personal OneDrive). Free Azure app registration — not Azure hosting.
    microsoft_tenant_id: str = "consumers"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_refresh_token: str = ""
    # Path under OneDrive root, e.g. PMS-Decision-Platform/DailyEditBackup
    onedrive_graph_folder: str = "PMS-Decision-Platform/DailyEditBackup"

    # --- Research analyst / Grok (optional) ---
    xai_api_key: str = ""
    xai_api_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-2-latest"
    research_index_enabled: bool = True
    research_corpus_globs: str = "**/*.pdf,**/*.md,**/*.txt"
    research_corpus_exclude_globs: str = "**/~*,**/.tmp/**"
    research_rag_max_chunks: int = 8
    research_rag_max_context_tokens: int = 4000
    research_rag_snippet_chars: int = 1200
    research_answer_cache_ttl_days: int = 30
    research_prompt_retention_days: int = 0
    research_analyst_prompt_version: str = "v1"

    @property
    def migration_database_url(self) -> str:
        """URL for Alembic / one-shot migration tasks (prefer direct when set)."""
        return self.database_direct_url or self.database_url


settings = Settings()
