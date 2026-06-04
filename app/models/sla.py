from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SLA(Base):
    __tablename__ = "slas"

    id: Mapped[int] = mapped_column(primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("workflow_steps.id"))
    max_minutes: Mapped[int]
    escalate_to_role_id: Mapped[int | None]
