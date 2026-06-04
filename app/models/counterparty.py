from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Counterparty(Base):
    """طرف حساب برای دستور پرداخت و سایر پرداخت‌های خارجی."""

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(255))
    party_type: Mapped[str] = mapped_column(
        String(20), default="company"
    )  # person | company
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sheba_number: Mapped[str | None] = mapped_column(String(26), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(24), nullable=True)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
