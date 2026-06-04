from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut


class AdHocTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=8000)
    assignee_id: int = Field(..., gt=0)
    due_at: datetime = Field(..., description="مهلت انجام کار")
    initial_comment: str | None = Field(None, max_length=8000)


class AdHocTaskStepCreate(BaseModel):
    comment: str = Field(..., min_length=1, max_length=8000)
    assignee_id: int | None = Field(None, gt=0)
    due_at: datetime | None = Field(None, description="مهلت انجام برای گیرنده بعدی")
    close_task: bool = False


class AdHocTaskStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    author_name: str | None = None
    comment: str
    assignee_id: int | None = None
    assignee_name: str | None = None
    created_at: datetime | None = None
    attachments: list[AttachmentOut] = Field(default_factory=list)


class AdHocTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    status: str
    created_by_id: int
    created_by_name: str | None = None
    current_assignee_id: int
    current_assignee_name: str | None = None
    due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    steps: list[AdHocTaskStepOut] = Field(default_factory=list)


class AdHocTaskListItem(BaseModel):
    id: int
    title: str
    status: str
    created_by_name: str | None = None
    current_assignee_name: str | None = None
    due_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdHocTaskListResponse(BaseModel):
    items: list[AdHocTaskListItem]
    total: int
    page: int
    pageSize: int


class UserLookupItem(BaseModel):
    id: int
    full_name: str | None = None
    username: str
