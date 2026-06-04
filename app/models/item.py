from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey
from app.core.database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    sku: Mapped[str] = mapped_column(String, unique=True)

    stocks: Mapped[list["Stock"]] = relationship(back_populates="item")

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))

    # 🔥 relation معکوس
    category = relationship("Category", back_populates="items")
