from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkflowDefinition(Base):
    """
    Defines approval chains per business ref_type (e.g. payment_request).
    steps_config is a JSON list of steps; each step is a list of role name aliases
    (first match wins), same shape as the former in-code WORKFLOW_ROLE_MATRIX values.
    """

    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(255))

    ref_type: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    steps_config: Mapped[list | None] = mapped_column(JSON, nullable=True)
