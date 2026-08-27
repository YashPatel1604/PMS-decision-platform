"""Resolve ReadContext from API query parameters."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Query, Request

from pms_platform.read_context import ReadContext, parse_read_context


def read_context_from_query(
    request: Request,
    view: str = Query(default="official"),
    change_request_id: uuid.UUID | None = Query(default=None),
) -> ReadContext:
    user = getattr(request.state, "user", None)
    viewer_id = user.user_id if user is not None else None
    try:
        return parse_read_context(
            view=view,
            viewer_user_id=viewer_id,
            change_request_id=change_request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
