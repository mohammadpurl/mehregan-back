from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GoodsReceipt(Base):
    """رسید ورود کالا (فاکتور خرید / تحویل انبار)."""

    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    proforma_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_proformas.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(30), default="draft")
    invoice_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    posted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        back_populates="grn", cascade="all, delete-orphan"
    )


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id", ondelete="CASCADE"))
    request_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_items.id"), nullable=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    quantity_received: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)

    grn: Mapped["GoodsReceipt"] = relationship(back_populates="lines")
