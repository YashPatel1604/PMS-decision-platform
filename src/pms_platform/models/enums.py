"""Domain enumerations."""

from enum import StrEnum


class EventType(StrEnum):
    """Transaction and corporate-action event types."""

    BUY = "Buy"
    SELL = "Sell"
    SPLIT = "Split"
    BONUS = "Bonus"
    RIGHTS = "Rights"
    DEMERGER = "Demerger"
    MERGER = "Merger"
    CONVERSION = "Conversion"

    @classmethod
    def corporate_actions(cls) -> frozenset["EventType"]:
        """Return event types treated as corporate actions."""
        return frozenset(
            {cls.SPLIT, cls.BONUS, cls.RIGHTS, cls.DEMERGER, cls.MERGER, cls.CONVERSION}
        )

    @classmethod
    def from_workbook(cls, value: str) -> "EventType":
        """Parse a workbook Buy/Sell cell value."""
        normalized = value.strip()
        for member in cls:
            if member.value.lower() == normalized.lower():
                return member
        msg = f"Unknown event type: {value!r}"
        raise ValueError(msg)


class DecisionType(StrEnum):
    """Investment decision event types."""

    INITIATE = "INITIATE"
    ADD = "ADD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    CORPORATE_ACTION = "CORPORATE_ACTION"


class EpisodeStatus(StrEnum):
    """Investment episode lifecycle status."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ValidationSeverity(StrEnum):
    """Validation issue severity."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
