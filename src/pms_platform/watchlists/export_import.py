"""Watchlist export and import (JSON / CSV)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import StringIO
from typing import Any

from sqlalchemy.orm import Session

from pms_platform.watchlists import service as wl

EXPORT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class WatchlistImportResult:
    watchlist_id: int
    watchlist_name: str
    members_added: int
    members_skipped: int


def export_watchlist_json(session: Session, watchlist_id: int) -> dict[str, Any]:
    watchlist = wl.get_watchlist(session, watchlist_id)
    members = wl.list_members(session, watchlist_id)
    return {
        "format_version": EXPORT_FORMAT_VERSION,
        "watchlist": {
            "name": watchlist.name,
            "description": watchlist.description,
            "is_default": watchlist.is_default,
        },
        "members": [
            {
                "display_name": member.display_name,
                "security_id": member.security_id,
                "nse_symbol": member.nse_symbol,
                "bse_code": member.bse_code,
                "isin": member.isin,
                "notes": member.notes,
                "resolution_status": member.resolution_status,
                "resolution_source": member.resolution_source,
            }
            for member in members
        ],
    }


def export_watchlist_json_text(session: Session, watchlist_id: int) -> str:
    return json.dumps(export_watchlist_json(session, watchlist_id), indent=2)


def export_watchlist_csv(session: Session, watchlist_id: int) -> str:
    wl.get_watchlist(session, watchlist_id)
    members = wl.list_members(session, watchlist_id)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "display_name",
            "security_id",
            "nse_symbol",
            "bse_code",
            "isin",
            "notes",
            "resolution_status",
        ]
    )
    for member in members:
        writer.writerow(
            [
                member.display_name,
                member.security_id or "",
                member.nse_symbol or "",
                member.bse_code or "",
                member.isin or "",
                member.notes or "",
                member.resolution_status,
            ]
        )
    return buffer.getvalue()


def import_watchlist_json(
    session: Session,
    payload: dict[str, Any],
    *,
    watchlist_id: int | None = None,
    create_name: str | None = None,
) -> WatchlistImportResult:
    """Import members from exported JSON into new or existing watchlist."""
    members_data = payload.get("members")
    if not isinstance(members_data, list):
        msg = "Import payload must include a members array"
        raise wl.WatchlistError(msg)

    if watchlist_id is not None:
        watchlist = wl.get_watchlist(session, watchlist_id)
    else:
        meta = payload.get("watchlist") or {}
        name = create_name or meta.get("name") or "Imported watchlist"
        description = meta.get("description")
        watchlist = wl.create_watchlist(session, name=str(name), description=description)

    added = 0
    skipped = 0
    for raw in members_data:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        try:
            wl.add_member(
                session,
                watchlist.watchlist_id,
                wl.MemberInput(
                    portfolio_name=raw.get("portfolio_name"),
                    security_id=raw.get("security_id"),
                    nse_symbol=raw.get("nse_symbol"),
                    bse_code=raw.get("bse_code"),
                    display_name=raw.get("display_name"),
                    notes=raw.get("notes"),
                ),
            )
            added += 1
        except wl.DuplicateMemberError:
            skipped += 1

    session.flush()
    return WatchlistImportResult(
        watchlist_id=watchlist.watchlist_id,
        watchlist_name=watchlist.name,
        members_added=added,
        members_skipped=skipped,
    )
