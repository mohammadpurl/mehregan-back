from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut
from app.schemas.money import MoneyAmount


class PettyCashExpenseLineIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str = Field(..., min_length=1, max_length=500)
    amount: MoneyAmount
    expense_date: date | None = Field(None, validation_alias="expenseDate")


class PettyCashExpenseLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    description: str
    amount: float
    expense_date: date | None = Field(None, serialization_alias="expenseDate")
    source: str
    row_order: int = Field(0, serialization_alias="rowOrder")


class PettyCashCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    amount: MoneyAmount
    reason: str | None = Field(None, max_length=2000)
    requested_date: date | None = Field(None, validation_alias="requestedDate")
    assignees_by_order: dict[str, int] | None = Field(
        None, validation_alias="assigneesByOrder"
    )


class PettyCashExpensesSubmit(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lines: list[PettyCashExpenseLineIn] = Field(..., min_length=1)
    replace_existing: bool = Field(True, validation_alias="replaceExisting")


class PettyCashOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    requester_id: int = Field(serialization_alias="requesterId")
    requester_name: str | None = Field(None, serialization_alias="requesterName")
    amount: float
    reason: str | None = None
    requested_date: date | None = Field(None, serialization_alias="requestedDate")
    status: str
    settlement_status: str = Field(serialization_alias="settlementStatus")
    payer_company_account_id: int | None = Field(
        None, serialization_alias="payerCompanyAccountId"
    )
    total_expenses: float | None = Field(None, serialization_alias="totalExpenses")
    settled_at: datetime | None = Field(None, serialization_alias="settledAt")
    workflow_instance_id: int | None = Field(
        None, serialization_alias="workflowInstanceId"
    )
    expense_lines: list[PettyCashExpenseLineOut] = Field(
        default_factory=list, serialization_alias="expenseLines"
    )
    attachments: list[AttachmentOut] = Field(default_factory=list)
    attachment_count: int = Field(0, serialization_alias="attachmentCount")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")


class PettyCashListResponse(BaseModel):
    items: list[PettyCashOut]
    total: int
    page: int
    pageSize: int


class PettyCashEligibilityOut(BaseModel):
    can_create: bool = Field(serialization_alias="canCreate")
    blocking_request_id: int | None = Field(
        None, serialization_alias="blockingRequestId"
    )
    message: str | None = None
