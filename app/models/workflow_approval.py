from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WorkflowApproval(Base):
    __tablename__ = "workflow_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)

    instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"))
    step_id: Mapped[int] = mapped_column(ForeignKey("workflow_steps.id"))

    approved_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String)

    comment: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
