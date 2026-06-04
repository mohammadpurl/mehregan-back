from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class SLARecord(Base):
    __tablename__ = "sla_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    step_id: Mapped[int] = mapped_column(ForeignKey("workflow_steps.id"))

    ref_id: Mapped[int]  # instance_id
    ref_type: Mapped[str]

    due_at: Mapped[datetime]
    is_triggered: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
