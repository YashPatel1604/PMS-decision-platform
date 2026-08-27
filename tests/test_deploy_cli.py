"""Deployment CLI smoke tests."""

from __future__ import annotations

from pms_platform.jobs.worker import run_worker_once


def test_worker_once_idle(session) -> None:
    """Empty queue: worker returns False without raising."""
    assert run_worker_once(session, worker_id="test-worker") is False
