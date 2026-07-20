"""کارهای پیش‌بینی‌نشده — ارجاع زنجیره‌ای بین کاربران."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"


class AdHocTask(Base):
    __tablename__ = "ad_hoc_tasks"
    __table_args__ = (
        Index("ix_ad_hoc_tasks_assignee_status", "current_assignee_id", "status"),
        Index("ix_ad_hoc_tasks_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    current_assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), default=STATUS_OPEN)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sla_notified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    steps = relationship(
        "AdHocTaskStep",
        back_populates="task",
        order_by="AdHocTaskStep.id",
        cascade="all, delete-orphan",
    )


class AdHocTaskStep(Base):
    __tablename__ = "ad_hoc_task_steps"
    __table_args__ = (Index("ix_ad_hoc_task_steps_task_id", "task_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("ad_hoc_tasks.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task = relationship("AdHocTask", back_populates="steps")
