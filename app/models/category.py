# app/models/category.py
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    items = relationship("Item", back_populates="category")
