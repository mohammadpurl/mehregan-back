from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, ForeignKey

from app.core.database import Base


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)

    quantity: Mapped[int] = mapped_column(Integer)

    po: Mapped["PurchaseOrder"] = relationship(back_populates="items")
