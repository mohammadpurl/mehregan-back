from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MissionRequest(Base):
    __tablename__ = "mission_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    destination: Mapped[str] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(Text)
    vehicle: Mapped[str] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )
