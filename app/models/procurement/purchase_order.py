from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id"), nullable=True)

    item_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="draft")

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="po", cascade="all, delete-orphan"
    )
