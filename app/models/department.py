from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    head_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    users = relationship(
        "User",
        back_populates="department",
        foreign_keys="User.department_id",
    )
    head = relationship("User", foreign_keys=[head_user_id])
