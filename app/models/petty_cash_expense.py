from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PettyCashExpenseLine(Base):
    __tablename__ = "petty_cash_expense_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    petty_cash_request_id: Mapped[int] = mapped_column(
        ForeignKey("petty_cash_requests.id", ondelete="CASCADE"),
        index=True,
    )

    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    row_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    petty_cash_request = relationship("PettyCashRequest", back_populates="expense_lines")
