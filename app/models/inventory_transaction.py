from datetime import datetime
from sqlalchemy import ForeignKey, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))

    type: Mapped[str] = mapped_column(String)
    # IN / OUT / TRANSFER

    quantity: Mapped[int] = mapped_column(Integer)

    ref_type: Mapped[str | None] = mapped_column(String)  # workflow / request / manual
    ref_id: Mapped[int | None] = mapped_column(Integer)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
