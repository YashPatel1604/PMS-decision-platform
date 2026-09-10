"""DailyEdit workbook upload, materialize, and DB reimport (cloud Option C)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pms_platform.config import settings
from pms_platform.domain.charts_rows import reimport_rows_from_parse
from pms_platform.domain.client_positions import reimport_client_positions
from pms_platform.market_data.charts_dashboard import parse_charts_range
from pms_platform.market_data.client_portfolio_parse import (
    clear_client_portfolio_cache,
)
from pms_platform.market_data.daily_edit_bhav import (
    charts_workbook_path,
    client_portfolio_daily_edit_path,
    pivot_workbook_daily_edit_path,
    sca_llp_workbook_path,
)
from pms_platform.models.source_lineage import SourceFile, SourceFileVersion
from pms_platform.storage.adapter import StorageAdapter, sha256_hex

DAILY_EDIT_CATEGORIES = frozenset({"client_portfolio", "charts", "sca_llp", "pivot_points"})

_REIMPORT_CATEGORIES = frozenset({"client_portfolio", "charts", "sca_llp", "pivot_points"})

_CATEGORY_BOOK = {"client_portfolio": "client", "sca_llp": "sca"}

_CANONICAL_FILENAMES = {
    "client_portfolio": "PMS_ClientPortfolio.xlsx",
    "charts": "Charts.xlsx",
    "sca_llp": "SCA_LLP Stock Holding.xlsx",
    "pivot_points": "PivotPoints.xlsx",
}


class DailyEditSyncError(Exception):
    """Business rule violation in DailyEdit sync."""


class DailyEditCloudUploadError(DailyEditSyncError):
    """Workbook saved locally but cloud archive failed."""

    def __init__(self, message: str, *, local_path: str) -> None:
        super().__init__(message)
        self.local_path = local_path


@dataclass(frozen=True)
class UploadResult:
    category: str
    filename: str
    checksum_sha256: str
    byte_size: int
    storage_key: str
    local_path: str
    deduplicated: bool


def _daily_edit_root() -> Path:
    if settings.daily_edit_dir is not None:
        return Path(settings.daily_edit_dir).expanduser()
    return Path("/data/daily_edit")


def _safe_filename(name: str) -> str:
    base = Path(name).name
    if not base or base.startswith("~$") or not base.lower().endswith(".xlsx"):
        raise DailyEditSyncError("filename must be a .xlsx workbook")
    return re.sub(r"[^\w.\- ()]", "_", base)


def _latest_version(session: Session, category: str) -> SourceFileVersion | None:
    return session.scalar(
        select(SourceFileVersion)
        .where(SourceFileVersion.category == category)
        .order_by(SourceFileVersion.created_at.desc())
        .limit(1)
    )


def _materialize_bytes(category: str, filename: str, data: bytes) -> Path:
    root = _daily_edit_root()
    root.mkdir(parents=True, exist_ok=True)
    dest_name = _CANONICAL_FILENAMES.get(category) or _safe_filename(filename)
    dest = root / dest_name
    dest.write_bytes(data)
    clear_client_portfolio_cache()
    return dest


def _latest_uploaded_path(session: Session, category: str) -> Path | None:
    version = _latest_version(session, category)
    if version is None:
        return None
    candidate = _daily_edit_root() / version.original_filename
    if candidate.is_file():
        return candidate
    canonical = _CANONICAL_FILENAMES.get(category)
    if canonical:
        path = _daily_edit_root() / canonical
        if path.is_file():
            return path
    return _workbook_path_for_category(category)


def upload_daily_edit(
    session: Session,
    *,
    category: str,
    filename: str,
    data: bytes,
    uploaded_by: int | None,
    storage: StorageAdapter,
    mime_type: str | None = None,
) -> UploadResult:
    if category not in DAILY_EDIT_CATEGORIES:
        raise DailyEditSyncError(f"unsupported category: {category}")
    if not data:
        raise DailyEditSyncError("empty file")

    safe_name = _safe_filename(filename)
    checksum = sha256_hex(data)
    latest = _latest_version(session, category)
    if latest is not None and latest.checksum_sha256 == checksum:
        local = _materialize_bytes(category, safe_name, data)
        return UploadResult(
            category=category,
            filename=safe_name,
            checksum_sha256=checksum,
            byte_size=len(data),
            storage_key=latest.storage_key,
            local_path=str(local),
            deduplicated=True,
        )

    storage_key = f"daily_edit/{category}/{checksum}/{safe_name}"
    local = _materialize_bytes(category, safe_name, data)
    try:
        storage.put(storage_key, data, content_type=mime_type)
    except Exception as exc:  # noqa: BLE001 — surface cloud failure after local save
        raise DailyEditCloudUploadError(
            f"saved to {local} but cloud upload failed: {exc}",
            local_path=str(local),
        ) from exc

    source = session.scalar(
        select(SourceFile).where(SourceFile.category == category).order_by(SourceFile.created_at.desc())
    )
    if source is None:
        source = SourceFile(category=category, display_name=safe_name)
        session.add(source)
        session.flush()

    version = SourceFileVersion(
        source_file_id=source.source_file_id,
        category=category,
        storage_key=storage_key,
        original_filename=safe_name,
        mime_type=mime_type,
        checksum_sha256=checksum,
        byte_size=len(data),
        uploaded_by=uploaded_by,
        parse_status="uploaded",
    )
    session.add(version)
    session.flush()
    source.display_name = safe_name
    source.active_version_id = version.source_file_version_id
    session.flush()

    return UploadResult(
        category=category,
        filename=safe_name,
        checksum_sha256=checksum,
        byte_size=len(data),
        storage_key=storage_key,
        local_path=str(local),
        deduplicated=False,
    )


def _workbook_path_for_category(category: str) -> Path | None:
    if category == "client_portfolio":
        return client_portfolio_daily_edit_path()
    if category == "charts":
        return charts_workbook_path()
    if category == "sca_llp":
        return sca_llp_workbook_path()
    if category == "pivot_points":
        return pivot_workbook_daily_edit_path()
    return None


def reimport_daily_edit(
    session: Session,
    *,
    category: str,
    update_qty: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if category not in _REIMPORT_CATEGORIES:
        raise DailyEditSyncError(f"reimport not supported for category: {category}")

    path = _latest_uploaded_path(session, category) or _workbook_path_for_category(category)
    if path is None or not path.is_file():
        raise DailyEditSyncError(f"no workbook on disk for {category} — upload first")

    if category in _CATEGORY_BOOK:
        from pms_platform.market_data.client_portfolio_parse import parse_client_portfolio_workbook

        try:
            book = parse_client_portfolio_workbook(path)
        except Exception as exc:  # noqa: BLE001
            raise DailyEditSyncError(f"workbook parse failed ({path.name}): {exc}") from exc
        if not book.model:
            raise DailyEditSyncError(
                f"no holdings in {path.name} — need Model and/or Quantity sheet with symbols"
            )
        holdings = [
            {
                "symbol": pos.symbol,
                "qty": float(pos.qty),
                "mcap_factor": float(pos.mcap_factor) if pos.mcap_factor is not None else None,
                "index_label": pos.index_label,
            }
            for pos in book.model
        ]
        book_key = _CATEGORY_BOOK[category]
        preview = reimport_client_positions(
            session,
            holdings,
            book=book_key,
            update_qty=update_qty,
            dry_run=True,
        )
        if dry_run:
            return {"category": category, "workbook": str(path), "dry_run": True, **preview}
        result = reimport_client_positions(
            session,
            holdings,
            book=book_key,
            update_qty=update_qty,
            dry_run=False,
        )
        return {"category": category, "workbook": str(path), "dry_run": False, **result}

    if category == "pivot_points":
        from pms_platform.market_data.pivot_seed import reimport_pivot_portfolio

        try:
            preview = reimport_pivot_portfolio(session, path, dry_run=True)
        except FileNotFoundError as exc:
            raise DailyEditSyncError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise DailyEditSyncError(f"pivot parse failed ({path.name}): {exc}") from exc
        if dry_run:
            return {"category": category, "workbook": str(path), "dry_run": True, **preview}
        result = reimport_pivot_portfolio(session, path, dry_run=False)
        return {"category": category, "workbook": str(path), "dry_run": False, **result}

    parsed = parse_charts_range(path)
    if not parsed:
        raise DailyEditSyncError("could not parse Charts Range sheet")
    preview = reimport_rows_from_parse(session, parsed, dry_run=True)
    if dry_run:
        return {"category": category, "workbook": str(path), "dry_run": True, **preview}
    result = reimport_rows_from_parse(session, parsed, dry_run=False)
    return {"category": category, "workbook": str(path), "dry_run": False, **result}


def daily_edit_status(session: Session) -> dict[str, Any]:
    root = _daily_edit_root()
    categories: dict[str, Any] = {}
    for category in sorted(DAILY_EDIT_CATEGORIES):
        version = _latest_version(session, category)
        path = _workbook_path_for_category(category)
        entry: dict[str, Any] = {
            "category": category,
            "reimport_supported": category in _REIMPORT_CATEGORIES,
            "uploaded": version is not None,
            "filename": version.original_filename if version else None,
            "checksum_sha256": version.checksum_sha256 if version else None,
            "uploaded_at": version.created_at.isoformat() if version else None,
            "on_disk": path is not None and path.is_file(),
            "local_path": str(path) if path else None,
        }
        if path is not None and path.is_file():
            entry["local_mtime"] = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
        categories[category] = entry
    return {
        "daily_edit_dir": str(root),
        "cloud_storage": settings.feature_cloud_storage,
        "categories": categories,
    }
