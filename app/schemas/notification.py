from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_read: bool | None = Field(None, validation_alias="isRead")


class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    type: str
    ref_id: int
    ref_type: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True  # ⬅ مهم (ORM mode جدید)
