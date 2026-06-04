from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String
from app.core.database import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)

    role_permissions = relationship("RolePermission", back_populates="permission")
    roles = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        viewonly=True,
    )
