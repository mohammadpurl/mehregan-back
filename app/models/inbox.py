from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InboxItem(Base):  # 👈 اسم را ثابت نگه می‌داریم
    __tablename__ = "inbox_items"
    __table_args__ = (
        Index("ix_inbox_user_done_read_created", "user_id", "is_done", "is_read", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(String(500))

    ref_id: Mapped[int | None] = mapped_column(Integer)
    ref_type: Mapped[str | None] = mapped_column(String(50))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
