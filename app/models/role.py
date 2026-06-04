from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Boolean, String
from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_singleton: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user_roles = relationship("UserRole", back_populates="role")
    role_permissions = relationship("RolePermission", back_populates="role")
    permissions = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        viewonly=True,
    )
