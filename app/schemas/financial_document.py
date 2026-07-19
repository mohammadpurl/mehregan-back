from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut
from app.schemas.money import MoneyAmount, OptionalMoneyAmount


class FinancialDocumentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_type: str = Field("check", validation_alias="documentType")
    title: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=2000)
    amount: OptionalMoneyAmount = None
    document_date: date | None = Field(None, validation_alias="documentDate")
    check_number: str | None = Field(None, max_length=100, validation_alias="checkNumber")
    party_name: str | None = Field(None, max_length=255, validation_alias="partyName")
    assignees_by_order: dict[str, int] | None = Field(default=None)


class FinancialDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    requester_id: int = Field(serialization_alias="requesterId")
    requester_name: str | None = Field(None, serialization_alias="requesterName")
    document_type: str = Field(serialization_alias="documentType")
    title: str | None = None
    description: str | None = None
    amount: float | None = None
    document_date: date | None = Field(None, serialization_alias="documentDate")
    check_number: str | None = Field(None, serialization_alias="checkNumber")
    party_name: str | None = Field(None, serialization_alias="partyName")
    status: str
    finance_confirmed_at: datetime | None = Field(
        None, serialization_alias="financeConfirmedAt"
    )
    sepidar_registered_at: datetime | None = Field(
        None, serialization_alias="sepidarRegisteredAt"
    )
    sepidar_registered_by: int | None = Field(
        None, serialization_alias="sepidarRegisteredBy"
    )
    sepidar_confirmed_at: datetime | None = Field(
        None, serialization_alias="sepidarConfirmedAt"
    )
    sepidar_confirmed_by: int | None = Field(
        None, serialization_alias="sepidarConfirmedBy"
    )
    workflow_instance_id: int | None = Field(
        None, serialization_alias="workflowInstanceId"
    )
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    attachments: list[AttachmentOut] = Field(default_factory=list)
    attachment_count: int = Field(0, serialization_alias="attachmentCount")
    can_upload: bool = Field(False, serialization_alias="canUpload")
    can_delete_attachment: bool = Field(
        False, serialization_alias="canDeleteAttachment"
    )


class FinancialDocumentListResponse(BaseModel):
    items: list[FinancialDocumentOut]
    total: int
    page: int
    pageSize: int
