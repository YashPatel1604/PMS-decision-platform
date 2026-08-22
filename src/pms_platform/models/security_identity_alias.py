"""Historical name/symbol aliases for canonical security identity."""

from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class SecurityIdentityAlias(Base):
    """Maps legacy watchlist/portfolio names and symbols to a canonical security."""

    __tablename__ = "security_identity_aliases"
    __table_args__ = (
        UniqueConstraint(
            "alias_type",
            "alias_value",
            "relationship_type",
            name="uq_security_identity_aliases_key",
        ),
    )

    alias_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id"), nullable=False
    )
    alias_name: Mapped[str | None] = mapped_column(String(256))
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    alias_value: Mapped[str] = mapped_column(String(256), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    historical_nse_symbol: Mapped[str | None] = mapped_column(String(32))
    historical_bse_code: Mapped[str | None] = mapped_column(String(16))
    historical_isin: Mapped[str | None] = mapped_column(String(16))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="watchlist_seed")
    notes: Mapped[str | None] = mapped_column(Text)
