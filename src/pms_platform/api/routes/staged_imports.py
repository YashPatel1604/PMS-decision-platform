"""Staged import API (validate → preview → approve → apply)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from pms_platform.api.deps import get_db
from pms_platform.approval.service import (
    ApprovalError,
    create_draft,
    user_has_permission,
)
from pms_platform.auth.permissions import PERMISSION_VIEW_ALL_SUBMITTED
from pms_platform.feature_flags import approval_workflow_enabled
from pms_platform.ingestion.staged_import import (
    STAGED_CATEGORIES,
    StagedImportError,
    apply_import_run,
    can_preview_import,
    preview_import_run,
    serialize_import_run,
    stage_import_bytes,
)
from pms_platform.models.source_lineage import ImportRun
from pms_platform.models.user import User
from pms_platform.storage import get_storage

router = APIRouter(prefix="/imports/staged", tags=["staged-imports"])


def _user(request: Request) -> User | None:
    return getattr(request.state, "user", None)


def _require_workflow() -> None:
    if not approval_workflow_enabled():
        raise HTTPException(status_code=503, detail="Approval workflow is disabled")


@router.post("")
async def post_staged_import(
    request: Request,
    category: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> dict:
    _require_workflow()
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if category not in STAGED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {sorted(STAGED_CATEGORIES)}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = stage_import_bytes(
            session,
            category=category.strip(),
            filename=file.filename or "upload.xlsx",
            data=data,
            uploaded_by=user.user_id,
            storage=get_storage(),
            mime_type=file.content_type,
        )
        session.commit()
    except StagedImportError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = preview_import_run(session, result.import_run_id)
    payload["deduplicated"] = result.deduplicated
    return payload


@router.get("/{import_run_id}")
def get_staged_import(
    import_run_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    _require_workflow()
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    can_all = user_has_permission(session, user, PERMISSION_VIEW_ALL_SUBMITTED)
    if not can_preview_import(run, viewer_user_id=user.user_id, can_view_all=can_all):
        raise HTTPException(status_code=403, detail="Preview not authorized until approved")
    return serialize_import_run(run)


@router.post("/{import_run_id}/request-approval")
def post_request_approval(
    import_run_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    _require_workflow()
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    if run.created_by != user.user_id:
        raise HTTPException(status_code=403, detail="Only uploader may request approval")
    if run.status not in ("validated",):
        raise HTTPException(status_code=400, detail=f"cannot request approval from status {run.status}")

    try:
        req = create_draft(
            session,
            proposer=user,
            title=f"Import {run.category}: {run.source_file_version.original_filename}",
            domain="import",
            reason=None,
            operations=[
                {
                    "entity_kind": "import_run",
                    "entity_id": str(run.import_run_id),
                    "operation_type": "apply",
                    "after_state": {
                        "category": run.category,
                        "checksum_sha256": run.checksum_sha256,
                    },
                }
            ],
        )
        run.status = "pending_approval"
        run.change_request_id = req.change_request_id
        session.commit()
    except ApprovalError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return {
        "import_run_id": str(run.import_run_id),
        "change_request_id": str(req.change_request_id),
        "status": run.status,
    }


@router.post("/{import_run_id}/apply")
def post_apply_import(
    import_run_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
) -> dict:
    """Apply a validated import directly (no Samir approval — D12)."""
    _require_workflow()
    user = _user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    run = session.get(ImportRun, import_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not found")
    if run.created_by != user.user_id and not user_has_permission(
        session, user, PERMISSION_VIEW_ALL_SUBMITTED
    ):
        raise HTTPException(status_code=403, detail="Not authorized to apply this import")
    try:
        apply_import_run(session, import_run_id, storage=get_storage())
        session.commit()
    except StagedImportError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return serialize_import_run(run)
