from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Integer
from app.core.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))

    quantity: Mapped[int] = mapped_column(Integer)

    item: Mapped["Item"] = relationship(back_populates="stocks")
    warehouse: Mapped["Warehouse"] = relationship(back_populates="stocks")
