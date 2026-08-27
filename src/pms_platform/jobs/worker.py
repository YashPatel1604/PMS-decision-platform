"""Job worker handlers and run loop."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from pms_platform.ingestion.staged_import import apply_import_run
from pms_platform.jobs.service import (
    claim_next_job,
    complete_job,
    drain_outbox_to_jobs,
    fail_job,
    release_stale_leases,
)
from pms_platform.models.change_request import Job

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]


def _handle_apply_import_run(session: Session, payload: dict[str, Any]) -> None:
    run_id = uuid.UUID(str(payload["import_run_id"]))
    apply_import_run(session, run_id)


def _handle_change_request_approved(session: Session, payload: dict[str, Any]) -> None:
    ops = payload.get("operations") or []
    for op in ops:
        if op.get("entity_kind") == "import_run" and op.get("entity_id"):
            apply_import_run(session, uuid.UUID(str(op["entity_id"])))


_HANDLERS: dict[str, Handler] = {
    "apply_import_run": _handle_apply_import_run,
    "outbox.change_request.approved": _handle_change_request_approved,
}


def dispatch_job(session: Session, job: Job) -> None:
    handler = _HANDLERS.get(job.job_type)
    if handler is None:
        raise ValueError(f"no handler for job type {job.job_type}")
    handler(session, dict(job.payload or {}))


def run_worker_once(session: Session, *, worker_id: str = "worker-1") -> bool:
    """Process outbox, claim one job, execute. Returns True if work was done."""
    release_stale_leases(session)
    drain_outbox_to_jobs(session)
    job = claim_next_job(session, worker_id=worker_id)
    if job is None:
        return False
    try:
        dispatch_job(session, job)
        complete_job(session, job)
    except Exception as exc:  # noqa: BLE001 — job failure is recorded and retried
        fail_job(session, job, str(exc))
        logger.exception("job %s failed: %s", job.job_id, exc)
    return True
