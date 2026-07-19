from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RequestItem(Base):
    __tablename__ = "request_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    supply_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # موجودی واردشده توسط سرپرست مالی (از سپیدار)
    warehouse_stock: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)

    quantity: Mapped[int] = mapped_column(Integer)

    request: Mapped["Request"] = relationship(back_populates="items")
