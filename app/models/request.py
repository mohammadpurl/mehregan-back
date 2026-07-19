from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String, default="internal")

    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")

    payment_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_requests.id"), nullable=True
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )
    approved_payment_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_payment_comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    payment_location: Mapped[str | None] = mapped_column(String(40), nullable=True)
    check_plan: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)

    invoice_paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    invoice_paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    sepidar_registered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sepidar_registered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    sepidar_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sepidar_confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    bol_uploaded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    goods_received_at: Mapped[datetime | None] = mapped_column(nullable=True)
    goods_received_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    warehouse_posted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    warehouse_posted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    items: Mapped[list["RequestItem"]] = relationship(back_populates="request")
