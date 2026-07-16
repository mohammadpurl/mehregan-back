from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PettyCashRequest(Base):
    __tablename__ = "petty_cash_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    settlement_status: Mapped[str] = mapped_column(String(50), default="NONE")

    payer_company_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_bank_accounts.id"), nullable=True
    )

    total_expenses: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    sepidar_registered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sepidar_registered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    sepidar_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sepidar_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    expense_lines = relationship(
        "PettyCashExpenseLine",
        back_populates="petty_cash_request",
        cascade="all, delete-orphan",
    )
