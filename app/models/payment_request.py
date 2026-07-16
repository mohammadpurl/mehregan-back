from datetime import datetime, date
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, Date
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    payer_company_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("company_bank_accounts.id"), nullable=True
    )
    receiver_counterparty_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparty_bank_accounts.id"), nullable=True
    )

    payment_type: Mapped[str] = mapped_column(String(50))
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(15, 2))

    payer_account: Mapped[str] = mapped_column(String(100))
    receiver_account: Mapped[str] = mapped_column(String(100))

    payment_date: Mapped[date | None] = mapped_column(Date)

    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="PENDING")

    # وام: توسط تأییدکننده (مدیر مالی / مدیر سیستم) پر می‌شود
    installment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_installment_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # مساعده: تاریخ تسویه توسط تأییدکننده
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # دستور پرداخت: انفرادی / جمعی
    payment_order_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_marked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_marked_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # تأیید سرپرست مالی: بررسی ثبت در سپیدار
    sepidar_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sepidar_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
