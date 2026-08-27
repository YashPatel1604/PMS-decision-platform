"""Staged import idempotency and preview authorization tests."""

from __future__ import annotations

import io

import openpyxl
import pytest

from pms_platform.approval.service import approve_request, submit_request
from pms_platform.auth.passwords import hash_password
from pms_platform.ingestion.staged_import import (
    apply_import_run,
    can_preview_import,
    stage_import_bytes,
)
from pms_platform.models.source_lineage import ImportRun
from pms_platform.models.user import User
from pms_platform.storage.adapter import LocalFilesystemStorage


def _xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "test"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    adapter = LocalFilesystemStorage(tmp_path / "private")
    monkeypatch.setattr("pms_platform.storage.get_storage", lambda: adapter)
    return adapter


def _user(session, *, email: str, role: str) -> User:
    u = User(
        email=email,
        password_hash=hash_password("x"),
        display_name=email.split("@")[0],
        role=role,
    )
    session.add(u)
    session.flush()
    return u


def test_duplicate_upload_is_idempotent(session, storage) -> None:
    user = _user(session, email="j@t.com", role="client")
    data = _xlsx_bytes()
    first = stage_import_bytes(
        session,
        category="portfolio_snapshots",
        filename="snap.xlsx",
        data=data,
        uploaded_by=user.user_id,
        storage=storage,
    )
    second = stage_import_bytes(
        session,
        category="portfolio_snapshots",
        filename="snap.xlsx",
        data=data,
        uploaded_by=user.user_id,
        storage=storage,
    )
    assert second.deduplicated is True
    assert second.import_run_id == first.import_run_id
    apply_import_run(session, first.import_run_id)
    third = stage_import_bytes(
        session,
        category="portfolio_snapshots",
        filename="snap.xlsx",
        data=data,
        uploaded_by=user.user_id,
        storage=storage,
    )
    assert third.deduplicated is True
    assert third.status == "applied"


def test_unapproved_preview_restricted(session, storage) -> None:
    julesh = _user(session, email="j@t.com", role="client")
    samir = _user(session, email="s@t.com", role="admin")
    other = _user(session, email="o@t.com", role="client")
    staged = stage_import_bytes(
        session,
        category="transactions",
        filename="tx.xlsx",
        data=_xlsx_bytes(),
        uploaded_by=julesh.user_id,
        storage=storage,
    )
    import_run = session.get(ImportRun, staged.import_run_id)
    assert import_run is not None
    assert can_preview_import(import_run, viewer_user_id=julesh.user_id, can_view_all=False)
    assert can_preview_import(import_run, viewer_user_id=samir.user_id, can_view_all=True)
    assert not can_preview_import(import_run, viewer_user_id=other.user_id, can_view_all=False)


def test_approve_import_via_worker(session, storage) -> None:
    from pms_platform.approval.service import create_draft

    julesh = _user(session, email="j2@t.com", role="client")
    samir = _user(session, email="s2@t.com", role="admin")
    staged = stage_import_bytes(
        session,
        category="portfolio_snapshots",
        filename="Portfolio_2024.xlsx",
        data=_xlsx_bytes(),
        uploaded_by=julesh.user_id,
        storage=storage,
    )
    req = create_draft(
        session,
        proposer=julesh,
        title="Import",
        domain="import",
        operations=[
            {
                "entity_kind": "import_run",
                "entity_id": str(staged.import_run_id),
                "operation_type": "apply",
            }
        ],
    )
    submit_request(session, actor=julesh, change_request_id=req.change_request_id)
    approve_request(session, reviewer=samir, change_request_id=req.change_request_id)
    session.flush()

    run = session.get(ImportRun, staged.import_run_id)
    assert run is not None
    assert run.status == "applied"


def test_direct_apply_without_approval(session, storage) -> None:
    user = _user(session, email="apply@t.com", role="client")
    staged = stage_import_bytes(
        session,
        category="portfolio_snapshots",
        filename="Portfolio_2024.xlsx",
        data=_xlsx_bytes(),
        uploaded_by=user.user_id,
        storage=storage,
    )
    run = session.get(ImportRun, staged.import_run_id)
    assert run is not None
    assert run.status == "validated"

    applied = apply_import_run(session, staged.import_run_id, storage=storage)
    assert applied.status == "applied"
    assert applied.applied_at is not None
    assert applied.row_counts.get("inserted") == 0
