from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyBankAccount(Base):
    """حساب‌های بانکی شرکت (مبدأ پرداخت)."""

    __tablename__ = "company_bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)

    label: Mapped[str] = mapped_column(String(120))
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sheba_number: Mapped[str | None] = mapped_column(String(26), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(24), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
