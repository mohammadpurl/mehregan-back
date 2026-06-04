from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer
from app.core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)

    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)

    manager = relationship("User", foreign_keys=[manager_id])
