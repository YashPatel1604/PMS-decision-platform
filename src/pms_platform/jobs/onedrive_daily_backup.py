"""Overwrite the four DailyEdit workbooks via Graph (or local folder fallback) at 19:00 IST."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from pms_platform.config import settings

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_MARKER_NAME = ".onedrive_backup_last_ist_date"

# Keep in sync with daily_edit_sync._CANONICAL_FILENAMES.
_CANONICAL = {
    "client_portfolio": "PMS_ClientPortfolio.xlsx",
    "charts": "Charts.xlsx",
    "sca_llp": "SCA_LLP Stock Holding.xlsx",
    "pivot_points": "PivotPoints.xlsx",
}


class DailyEditBackupError(RuntimeError):
    """DailyEdit backup failure."""


def _daily_edit_root() -> Path:
    if settings.daily_edit_dir is not None:
        return Path(settings.daily_edit_dir).expanduser()
    return Path("/data/daily_edit")


def _backup_root() -> Path:
    if settings.onedrive_backup_dir is not None:
        return Path(settings.onedrive_backup_dir).expanduser()
    return _daily_edit_root().parent / "DailyEditBackup"


def _graph_folder() -> str:
    return settings.onedrive_graph_folder.strip().strip("/").replace("\\", "/")


def _marker_path() -> Path:
    # Prefer backup dir when local; else daily_edit (Railway volume).
    try:
        root = _backup_root()
        root.mkdir(parents=True, exist_ok=True)
        return root / _MARKER_NAME
    except OSError:
        root = _daily_edit_root()
        root.mkdir(parents=True, exist_ok=True)
        return root / _MARKER_NAME


def _use_graph() -> bool:
    from pms_platform.storage.onedrive_graph import credentials_configured

    return credentials_configured()


def resolve_backup_bytes(session: Session | None, category: str) -> tuple[str, bytes] | None:
    """Prefer live DailyEdit disk copy; else latest storage version."""
    filename = _CANONICAL.get(category)
    if not filename:
        return None
    local = _daily_edit_root() / filename
    if local.is_file():
        return filename, local.read_bytes()
    if session is None:
        return None
    from sqlalchemy import select

    from pms_platform.models.source_lineage import SourceFileVersion

    version = session.scalar(
        select(SourceFileVersion)
        .where(SourceFileVersion.category == category)
        .order_by(SourceFileVersion.created_at.desc())
        .limit(1)
    )
    if version is None or not version.storage_key:
        return None
    from pms_platform.storage import get_storage

    try:
        return filename, get_storage().get(version.storage_key)
    except Exception as exc:  # noqa: BLE001 — skip category, continue others
        logger.warning("storage get failed for %s: %s", category, exc)
        return None


def run_onedrive_daily_backup(session: Session | None = None) -> dict[str, Any]:
    """Overwrite Client + Charts + SCA + Pivot (same filenames). Graph if creds set."""
    if not settings.onedrive_backup_enabled:
        raise DailyEditBackupError("ONEDRIVE_BACKUP_ENABLED is off")

    use_graph = _use_graph()
    token: str | None = None
    dest_root: Path | None = None
    folder = _graph_folder()

    if use_graph:
        from pms_platform.storage.onedrive_graph import access_token_from_refresh

        token = access_token_from_refresh()
    else:
        dest_root = _backup_root()
        dest_root.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, Any]] = []
    missing: list[str] = []
    errors: list[str] = []

    for category in sorted(_CANONICAL):
        resolved = resolve_backup_bytes(session, category)
        if resolved is None:
            missing.append(category)
            continue
        filename, data = resolved
        try:
            if use_graph:
                from pms_platform.storage.onedrive_graph import put_drive_file

                assert token is not None
                remote = f"{folder}/{filename}" if folder else filename
                put_drive_file(remote, data, access_token=token)
                uploaded.append(
                    {
                        "category": category,
                        "filename": filename,
                        "path": remote,
                        "bytes": len(data),
                    }
                )
            else:
                assert dest_root is not None
                dest = dest_root / filename
                dest.write_bytes(data)
                uploaded.append(
                    {
                        "category": category,
                        "filename": filename,
                        "path": str(dest),
                        "bytes": len(data),
                    }
                )
        except Exception as exc:  # noqa: BLE001 — collect per-file errors
            errors.append(f"{category}: {exc}")

    result = {
        "ok": not errors and len(uploaded) == len(_CANONICAL),
        "uploaded": uploaded,
        "missing": missing,
        "errors": errors,
        "folder": folder if use_graph else str(dest_root),
        "via": "graph" if use_graph else "local",
    }
    if errors:
        raise DailyEditBackupError(
            "daily edit backup partial failure: " + "; ".join(errors)
        )
    return result


def maybe_run_onedrive_daily_backup(session: Session | None = None) -> dict[str, Any] | None:
    """Run once after ONEDRIVE_BACKUP_HOUR_IST (default 19:00) Asia/Kolkata."""
    if not settings.onedrive_backup_enabled:
        return None
    now = datetime.now(IST)
    hour = int(settings.onedrive_backup_hour_ist)
    if now.hour < hour:
        return None
    today = now.date().isoformat()
    marker = _marker_path()
    try:
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == today:
            return None
    except OSError:
        pass

    logger.info("daily edit backup starting (IST %s hour>=%s)", today, hour)
    result = run_onedrive_daily_backup(session)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(today, encoding="utf-8")
    except OSError as exc:
        logger.warning("could not write backup marker: %s", exc)
    logger.info(
        "daily edit backup done via %s: %s written → %s missing=%s",
        result.get("via"),
        len(result.get("uploaded") or []),
        result.get("folder"),
        result.get("missing"),
    )
    return result
