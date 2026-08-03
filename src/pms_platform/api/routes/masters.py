"""Final Master Excel browse + prompt-update API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pms_platform.api.routes.episodes import get_db
from pms_platform.masters.apply import apply_edits
from pms_platform.masters.parser import edit_from_dict, edit_to_dict, parse_prompt
from pms_platform.masters.paths import MasterKind, list_workbooks, resolve_master_path
from pms_platform.masters.preview import preview_workbook

router = APIRouter()


class MasterWorkbookResponse(BaseModel):
    kind: str
    label: str
    path: str
    exists: bool
    default_sheet: str
    mtime: str | None
    size_bytes: int | None
    raw_sync_path: str | None


class MasterPreviewResponse(BaseModel):
    kind: str
    path: str
    sheet: str
    sheets: list[str]
    columns: list[str]
    rows: list[dict]
    offset: int
    limit: int
    total_rows: int
    matched_rows: int


class ProposedEditResponse(BaseModel):
    action: str
    kind: str
    line_number: int
    raw_line: str
    fields: dict
    summary: str
    warnings: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    prompt: str
    kind: str | None = None


class ParseResponse(BaseModel):
    edits: list[ProposedEditResponse]
    errors: list[str]
    can_apply: bool


class ApplyRequest(BaseModel):
    edits: list[dict] | None = None
    prompt: str | None = None
    kind: str | None = None
    reimport: bool = True


class ApplyResponse(BaseModel):
    applied: int
    backups: list[str]
    written_paths: list[str]
    synced_raw: list[str]
    import_notes: list[str]
    errors: list[str]
    episode_count: int | None = None


def _parse_kind(kind: str) -> MasterKind:
    try:
        return MasterKind(kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="kind must be one of: security, transactions, sell_since",
        ) from exc


@router.get("", response_model=list[MasterWorkbookResponse])
def get_masters() -> list[MasterWorkbookResponse]:
    """List Final Master workbooks and resolved paths."""
    return [
        MasterWorkbookResponse(
            kind=info.kind.value,
            label=info.label,
            path=str(info.path),
            exists=info.exists,
            default_sheet=info.default_sheet,
            mtime=info.mtime,
            size_bytes=info.size_bytes,
            raw_sync_path=str(info.raw_sync_path) if info.raw_sync_path else None,
        )
        for info in list_workbooks()
    ]


@router.get("/{kind}/preview", response_model=MasterPreviewResponse)
def get_master_preview(
    kind: str,
    sheet: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    q: str | None = None,
) -> MasterPreviewResponse:
    master_kind = _parse_kind(kind)
    try:
        preview = preview_workbook(
            master_kind, sheet=sheet, offset=offset, limit=limit, q=q
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MasterPreviewResponse(
        kind=preview.kind.value,
        path=preview.path,
        sheet=preview.sheet,
        sheets=preview.sheets,
        columns=preview.columns,
        rows=preview.rows,
        offset=preview.offset,
        limit=preview.limit,
        total_rows=preview.total_rows,
        matched_rows=preview.matched_rows,
    )


@router.get("/{kind}/download")
def download_master(kind: str) -> FileResponse:
    master_kind = _parse_kind(kind)
    path = resolve_master_path(master_kind)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Workbook not found: {path}")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@router.post("/parse", response_model=ParseResponse)
def parse_master_prompt(body: ParseRequest) -> ParseResponse:
    kind = _parse_kind(body.kind) if body.kind else None
    result = parse_prompt(body.prompt, kind=kind)
    return ParseResponse(
        edits=[ProposedEditResponse(**edit_to_dict(e)) for e in result.edits],
        errors=result.errors,
        can_apply=bool(result.edits) and not result.errors,
    )


@router.post("/apply", response_model=ApplyResponse)
def apply_master_edits(
    body: ApplyRequest,
    session: Session = Depends(get_db),
) -> ApplyResponse:
    edits_payload = body.edits
    if not edits_payload:
        if not body.prompt:
            raise HTTPException(status_code=400, detail="Provide edits or prompt")
        kind = _parse_kind(body.kind) if body.kind else None
        parsed = parse_prompt(body.prompt, kind=kind)
        if parsed.errors:
            raise HTTPException(
                status_code=400,
                detail={"message": "Prompt has errors", "errors": parsed.errors},
            )
        edits_payload = [edit_to_dict(e) for e in parsed.edits]

    try:
        edits = [edit_from_dict(item) for item in edits_payload]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid edits: {exc}") from exc

    try:
        result = apply_edits(session, edits, reimport=body.reimport)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ApplyResponse(
        applied=result.applied,
        backups=result.backups,
        written_paths=result.written_paths,
        synced_raw=result.synced_raw,
        import_notes=result.import_notes,
        errors=result.errors,
        episode_count=result.episode_count,
    )
