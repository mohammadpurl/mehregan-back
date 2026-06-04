from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.workflow_instance import WorkflowInstance


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True)

    instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"))

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    order: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String, default="pending")

    approved_by: Mapped[int | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)

    assigned_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="steps")
