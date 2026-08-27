"""Official vs working read contexts for centralized approval workflow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class ReadMode(str, Enum):
    """How domain services overlay draft/submitted change operations."""

    OFFICIAL = "official"
    MINE = "mine"
    PROPOSAL = "proposal"


@dataclass(frozen=True, slots=True)
class ReadContext:
    """Passed into repositories/calculators instead of ad-hoc role checks."""

    mode: ReadMode
    viewer_user_id: int | None = None
    change_request_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.mode == ReadMode.PROPOSAL and self.change_request_id is None:
            raise ValueError("change_request_id required for proposal mode")
        if self.mode == ReadMode.MINE and self.viewer_user_id is None:
            raise ValueError("viewer_user_id required for mine mode")

    @classmethod
    def official(cls) -> ReadContext:
        return cls(mode=ReadMode.OFFICIAL)

    @classmethod
    def mine(cls, viewer_user_id: int) -> ReadContext:
        return cls(mode=ReadMode.MINE, viewer_user_id=viewer_user_id)

    @classmethod
    def proposal(cls, *, viewer_user_id: int, change_request_id: UUID) -> ReadContext:
        return cls(
            mode=ReadMode.PROPOSAL,
            viewer_user_id=viewer_user_id,
            change_request_id=change_request_id,
        )

    @property
    def includes_pending_overlay(self) -> bool:
        return self.mode in (ReadMode.MINE, ReadMode.PROPOSAL)


def parse_read_context(
    *,
    view: str | None,
    viewer_user_id: int | None,
    change_request_id: UUID | None,
) -> ReadContext:
    """Parse API query params into a validated ReadContext."""
    key = (view or "official").strip().lower()
    if key == "official":
        return ReadContext.official()
    if key == "mine":
        if viewer_user_id is None:
            raise ValueError("viewer_user_id required for view=mine")
        return ReadContext.mine(viewer_user_id)
    if key == "proposal":
        if viewer_user_id is None or change_request_id is None:
            raise ValueError("viewer_user_id and change_request_id required for view=proposal")
        return ReadContext.proposal(
            viewer_user_id=viewer_user_id, change_request_id=change_request_id
        )
    raise ValueError(f"unknown view: {view}")
