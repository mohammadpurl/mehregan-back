from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer
from app.core.database import Base


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(primary_key=True)

    ref_id: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str] = mapped_column(String)

    status: Mapped[str] = mapped_column(String, default="pending")

    steps: Mapped[list["WorkflowStep"]] = relationship(back_populates="instance")
