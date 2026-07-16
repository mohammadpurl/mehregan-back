from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FinancialDocument(Base):
    __tablename__ = "financial_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    document_type: Mapped[str] = mapped_column(String(30), default="check")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    check_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    party_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    finance_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)

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
