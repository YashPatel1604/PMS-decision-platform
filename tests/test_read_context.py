"""Tests for ReadContext parsing and invariants."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pms_platform.read_context import ReadContext, ReadMode, parse_read_context


def test_official_context() -> None:
    ctx = ReadContext.official()
    assert ctx.mode == ReadMode.OFFICIAL
    assert not ctx.includes_pending_overlay


def test_mine_requires_user() -> None:
    with pytest.raises(ValueError):
        ReadContext(mode=ReadMode.MINE)
    ctx = ReadContext.mine(42)
    assert ctx.includes_pending_overlay


def test_parse_read_context() -> None:
    assert parse_read_context(view="official", viewer_user_id=None, change_request_id=None).mode == ReadMode.OFFICIAL
    assert parse_read_context(view="mine", viewer_user_id=1, change_request_id=None).viewer_user_id == 1


def test_proposal_requires_ids() -> None:
    rid = uuid4()
    ctx = parse_read_context(view="proposal", viewer_user_id=1, change_request_id=rid)
    assert ctx.change_request_id == rid
