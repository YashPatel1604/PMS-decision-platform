"""Security ORM model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pms_platform.db.base import Base


class Security(Base):
    """Investable equity security from the Security Master."""

    __tablename__ = "securities"

    security_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    portfolio_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    canonical_name: Mapped[str | None] = mapped_column(String(256))
    current_nse_symbol: Mapped[str | None] = mapped_column(String(32))
    historical_nse_symbol: Mapped[str | None] = mapped_column(String(32))
    bse_code: Mapped[str | None] = mapped_column(String(16))
    isin: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(32))
    sector: Mapped[str | None] = mapped_column(String(128))
    industry: Mapped[str | None] = mapped_column(String(128))
    corporate_history: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[str | None] = mapped_column(String(128))
    import_batch_id: Mapped[int | None] = mapped_column()

    transactions = relationship("Transaction", back_populates="security")
