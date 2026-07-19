from datetime import datetime, date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WarehouseForm(Base):
    __tablename__ = "warehouse_forms"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    form_type: Mapped[str] = mapped_column(String(20))
    # IN / OUT / TRANSFER
    source: Mapped[str | None] = mapped_column(String(255))
    destination: Mapped[str | None] = mapped_column(String(255))
    receiver_name: Mapped[str | None] = mapped_column(String(255))
    effective_date: Mapped[date | None] = mapped_column(Date)

    description: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(50), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
