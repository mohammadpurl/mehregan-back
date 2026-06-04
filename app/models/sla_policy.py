from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SlaPolicy(Base):
    """
    SLA per workflow ref_type and step order (not per runtime workflow_step row).
  """

    __tablename__ = "sla_policies"
    __table_args__ = (
        UniqueConstraint(
            "ref_type",
            "step_order",
            name="uq_sla_policy_ref_type_step",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    ref_type: Mapped[str] = mapped_column(String(80), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    max_minutes: Mapped[int] = mapped_column(Integer)
    escalate_to_role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
