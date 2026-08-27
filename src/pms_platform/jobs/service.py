"""Postgres-backed job queue and outbox helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pms_platform.models.change_request import Job, OutboxEvent

JOB_LEASE_SECONDS = 120


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    priority: int = 0,
) -> Job:
    if idempotency_key:
        existing = session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    job = Job(
        job_type=job_type,
        payload=payload,
        idempotency_key=idempotency_key,
        priority=priority,
        status="pending",
    )
    session.add(job)
    session.flush()
    return job


def emit_outbox(
    session: Session,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    event = OutboxEvent(event_type=event_type, payload=payload)
    session.add(event)
    session.flush()
    return event


def drain_outbox_to_jobs(session: Session) -> int:
    """Create jobs for unprocessed outbox events (same transaction)."""
    events = session.scalars(
        select(OutboxEvent).where(OutboxEvent.processed_at.is_(None)).order_by(OutboxEvent.created_at)
    ).all()
    created = 0
    now = datetime.now(UTC)
    for event in events:
        key = f"outbox:{event.outbox_event_id}"
        enqueue_job(
            session,
            job_type=f"outbox.{event.event_type}",
            payload={"outbox_event_id": str(event.outbox_event_id), **(event.payload or {})},
            idempotency_key=key,
        )
        event.processed_at = now
        created += 1
    return created


def claim_next_job(session: Session, *, worker_id: str) -> Job | None:
    """Claim one pending job (SKIP LOCKED on Postgres)."""
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=JOB_LEASE_SECONDS)
    stmt = (
        select(Job)
        .where(
            Job.status == "pending",
            Job.available_at <= now,
            Job.attempts < Job.max_attempts,
        )
        .order_by(Job.priority.desc(), Job.available_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.scalars(stmt).first()
    if job is None:
        return None
    job.status = "running"
    job.lease_owner = worker_id
    job.lease_expires_at = lease_until
    job.attempts = job.attempts + 1
    session.flush()
    return job


def complete_job(session: Session, job: Job) -> None:
    job.status = "completed"
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = None


def fail_job(session: Session, job: Job, error: str) -> None:
    job.last_error = error[:2000]
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "pending"
        job.available_at = datetime.now(UTC) + timedelta(seconds=min(60 * job.attempts, 300))


def release_stale_leases(session: Session) -> int:
    now = datetime.now(UTC)
    result = session.execute(
        update(Job)
        .where(
            Job.status == "running",
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
        )
        .values(status="pending", lease_owner=None, lease_expires_at=None)
    )
    return int(result.rowcount or 0)
