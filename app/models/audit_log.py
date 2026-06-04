from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    entity: Mapped[str] = mapped_column(String(50))  # item
    entity_id: Mapped[int] = mapped_column(Integer)

    action: Mapped[str] = mapped_column(String(50))  # create/update/delete

    old_data: Mapped[str | None] = mapped_column(Text)
    new_data: Mapped[str | None] = mapped_column(Text)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
