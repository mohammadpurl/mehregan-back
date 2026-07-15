from datetime import datetime

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import ROOT_PATH
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    national_id: Mapped[str | None] = mapped_column(
        String(10), unique=True, nullable=True, index=True
    )
    father_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(24), nullable=True)
    sheba_number: Mapped[str | None] = mapped_column(String(26), nullable=True)
    profile_pic: Mapped[str | None] = mapped_column(String(500), nullable=True)

    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True)

    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    department = relationship(
        "Department",
        back_populates="users",
        foreign_keys=[department_id],
    )
    manager = relationship("User", remote_side="User.id")
    user_roles = relationship("UserRole", back_populates="user")

    def get_roles(self):
        return [ur.role for ur in self.user_roles if ur.is_active]

    def has_role(self, role_name: str):
        return any(r.name == role_name for r in self.get_roles())

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.last_name]
        name = " ".join(p.strip() for p in parts if p and p.strip())
        return name or self.username

    def profile_pic_url(self, cache_bust: int | None = None) -> str:
        if not self.profile_pic:
            return ""
        path = self.profile_pic.replace("\\", "/").lstrip("/")
        url = f"/uploads/{path}"
        if ROOT_PATH:
            url = f"{ROOT_PATH}{url}"
        if cache_bust is not None:
            url = f"{url}?v={cache_bust}"
        return url
