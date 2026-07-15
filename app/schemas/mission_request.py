from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut


class MissionRequestCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    destination: str = Field(..., min_length=1, max_length=500)
    reason: str = Field(..., min_length=1, max_length=8000)
    vehicle: str = Field(..., min_length=1, max_length=255)
    assignees_by_order: dict[str, int] | None = Field(
        None, validation_alias=AliasChoices("assigneesByOrder", "assignees_by_order")
    )


class MissionReportSubmit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    report_text: str = Field(
        ...,
        min_length=1,
        max_length=20000,
        validation_alias=AliasChoices("reportText", "report_text"),
    )


class MissionRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    requester_id: int = Field(serialization_alias="requesterId")
    requester_name: str | None = Field(None, serialization_alias="requesterName")
    destination: str
    reason: str
    vehicle: str
    status: str
    report_text: str | None = Field(None, serialization_alias="reportText")
    reported_at: datetime | None = Field(None, serialization_alias="reportedAt")
    workflow_instance_id: int | None = Field(None, serialization_alias="workflowInstanceId")
    attachments: list[AttachmentOut] = Field(default_factory=list)
    attachment_count: int = Field(0, serialization_alias="attachmentCount")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(None, serialization_alias="updatedAt")


class MissionRequestListResponse(BaseModel):
    items: list[MissionRequestOut]
    total: int
    page: int
    pageSize: int
