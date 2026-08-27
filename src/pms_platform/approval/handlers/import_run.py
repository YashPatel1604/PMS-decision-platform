"""Apply approved import runs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from pms_platform.approval.handlers.registry import register_handler
from pms_platform.ingestion.staged_import import apply_import_run
from pms_platform.jobs.service import enqueue_job


class ImportRunHandler:
    entity_kind = "import_run"

    def validate_operation(self, operation: dict[str, Any]) -> dict[str, Any]:
        if not operation.get("entity_id"):
            raise ValueError("entity_id required")
        return {"ok": True}

    def apply_operation(self, session: Session, operation: dict[str, Any]) -> None:
        run_id = uuid.UUID(str(operation["entity_id"]))
        apply_import_run(session, run_id)
        enqueue_job(
            session,
            job_type="apply_import_run",
            payload={"import_run_id": str(run_id)},
            idempotency_key=f"apply_import:{run_id}",
        )


_handler = ImportRunHandler()
register_handler(_handler)
