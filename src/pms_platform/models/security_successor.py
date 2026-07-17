"""Security successor chain ORM model."""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pms_platform.db.base import Base


class SecuritySuccessor(Base):
    """Successor mapping after rename, merger, or demerger."""

    __tablename__ = "security_successors"
    __table_args__ = (
        UniqueConstraint(
            "predecessor_security_id",
            "successor_security_id",
            "effective_date",
            "action_type",
            name="uq_security_successors_chain",
        ),
        UniqueConstraint("source_key", name="uq_security_successors_source_key"),
    )

    successor_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    predecessor_security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id"), nullable=False
    )
    successor_security_id: Mapped[str] = mapped_column(
        ForeignKey("securities.security_id"), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.import_batch_id"), nullable=False
    )
