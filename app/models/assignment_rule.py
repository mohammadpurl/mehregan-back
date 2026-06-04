from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String

from app.core.database import Base


class AssignmentRule(Base):
    __tablename__ = "assignment_rules"

    id: Mapped[int] = mapped_column(primary_key=True)

    role_id: Mapped[int] = mapped_column(Integer)

    strategy: Mapped[str] = mapped_column(String)
    # round_robin | least_loaded | random

    is_active: Mapped[bool] = mapped_column(default=True)
