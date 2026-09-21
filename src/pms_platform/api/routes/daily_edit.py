"""DailyEdit workbook upload and confirm-to-apply (cloud staging)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_db
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.ingestion.daily_edit_sync import (
    DAILY_EDIT_CATEGORIES,
    REIMPORT_CATEGORIES,
    DailyEditCloudUploadError,
    DailyEditSyncError,
    daily_edit_status,
    reimport_daily_edit,
    upload_daily_edit,
)
from pms_platform.models.user import User
from pms_platform.storage import get_storage

router = APIRouter(prefix="/daily-edit", tags=["daily-edit"])


def _user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def _require_user(request: Request) -> User:
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get("/status")
def get_status(request: Request, session: Session = Depends(get_db)) -> dict:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=503, detail="Approval workflow is disabled")
    _require_user(request)
    return daily_edit_status(session)


@router.post("/upload")
async def post_upload(
    request: Request,
    category: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    """Store workbook and return a dry-run preview. Does not change live numbers."""
    if not approval_workflow_enabled():
        raise HTTPException(status_code=503, detail="Approval workflow is disabled")
    user = _require_user(request)

    cat = category.strip()
    if cat not in DAILY_EDIT_CATEGORIES:
        raise HTTPException(
            status_code=400, detail=f"category must be one of {sorted(DAILY_EDIT_CATEGORIES)}"
        )
    data = await file.read()
    pending: dict | None = None
    try:
        result = upload_daily_edit(
            session,
            category=cat,
            filename=file.filename or "upload.xlsx",
            data=data,
            uploaded_by=user.user_id,
            storage=get_storage(),
            mime_type=file.content_type,
        )
        if cat in REIMPORT_CATEGORIES:
            pending = reimport_daily_edit(
                session,
                category=cat,
                dry_run=True,
                update_qty=True,
                authoritative=True,
            )
        session.commit()
    except DailyEditCloudUploadError as exc:
        session.rollback()
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except DailyEditSyncError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not write workbook to daily edit dir: {exc}",
        ) from exc
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "category": result.category,
        "filename": result.filename,
        "checksum_sha256": result.checksum_sha256,
        "byte_size": result.byte_size,
        "local_path": result.local_path,
        "deduplicated": result.deduplicated,
        "applied": None,
        "pending": pending,
    }


def _form_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@router.post("/reimport")
def post_reimport(
    request: Request,
    category: str = Form(...),
    update_qty: str | bool = Form(False),
    dry_run: str | bool = Form(True),
    authoritative: str | bool = Form(False),
    session: Session = Depends(get_db),
) -> dict:
    """Preview (dry_run) or confirm new numbers into the live DB (Julesh or admin)."""
    if not approval_workflow_enabled():
        raise HTTPException(status_code=503, detail="Approval workflow is disabled")
    _require_user(request)

    cat = category.strip()
    dry = _form_bool(dry_run)
    qty = _form_bool(update_qty)
    auth = _form_bool(authoritative)
    try:
        result = reimport_daily_edit(
            session,
            category=cat,
            update_qty=qty,
            dry_run=dry,
            authoritative=auth,
        )
        if not dry:
            session.commit()
    except DailyEditSyncError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
