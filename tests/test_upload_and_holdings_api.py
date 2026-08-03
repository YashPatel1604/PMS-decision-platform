"""Upload pipeline and API smoke tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from pms_platform.api.main import app
from pms_platform.ingestion.upload_pipeline import (
    commit_upload,
    stage_upload,
    validate_upload,
)


def _write_dummy_xlsx(path: Path) -> None:
    workbook = Workbook()
    workbook.active["A1"] = "dummy"
    workbook.save(path)


def test_stage_and_validate_snapshot_records_parse_error(session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.ingestion.upload_pipeline.settings.upload_dir",
        tmp_path,
    )
    path = tmp_path / "bad.xlsx"
    _write_dummy_xlsx(path)

    state = stage_upload(
        session,
        kind="portfolio_snapshots",
        filename="not_a_portfolio.xlsx",
        content=path.read_bytes(),
    )
    assert state.status == "staged"

    validated = validate_upload(session, state.batch_id)
    assert validated.status == "validation_failed"
    assert validated.error_count >= 1
    assert validated.can_commit is False


def test_commit_blocked_when_validation_has_errors(session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "pms_platform.ingestion.upload_pipeline.settings.upload_dir",
        tmp_path,
    )
    path = tmp_path / "bad.xlsx"
    _write_dummy_xlsx(path)
    state = stage_upload(
        session,
        kind="portfolio_snapshots",
        filename="not_a_portfolio.xlsx",
        content=path.read_bytes(),
    )
    validate_upload(session, state.batch_id)

    with pytest.raises(ValueError, match="validation errors"):
        commit_upload(session, state.batch_id)


def test_holdings_and_imports_endpoints_exist() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/holdings/open" in paths
    assert "/holdings/open/{episode_id}" in paths
    assert "/imports/upload" in paths
    assert "/imports/{batch_id}/validate" in paths
    assert "/imports/{batch_id}/commit" in paths
    assert "/imports/{batch_id}" in paths

    upload = client.post(
        "/imports/upload",
        data={"kind": "transactions"},
    )
    assert upload.status_code == 422
