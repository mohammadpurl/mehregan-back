from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut
from app.schemas.bank_account import BankAccountOut

PaymentAttachmentOut = AttachmentOut


class CounterpartyBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    party_type: str = Field(serialization_alias="partyType")
    company_name: str | None = Field(None, serialization_alias="companyName")
    account_number: str | None = Field(None, serialization_alias="accountNumber")
    sheba_number: str | None = Field(None, serialization_alias="shebaNumber")
    card_number: str | None = Field(None, serialization_alias="cardNumber")


class PaymentRequestOut(BaseModel):
    """قرارداد فرانت (camelCase در خروجی JSON)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    requester_id: int = Field(serialization_alias="requesterId")
    counterparty_id: int | None = Field(None, serialization_alias="counterpartyId")
    counterparty: CounterpartyBriefOut | None = None
    payment_type: str = Field(serialization_alias="paymentType")
    payment_method: str | None = Field(None, serialization_alias="paymentMethod")
    amount: float
    payer_company_account_id: int | None = Field(
        None, serialization_alias="payerCompanyAccountId"
    )
    receiver_counterparty_account_id: int | None = Field(
        None, serialization_alias="receiverCounterpartyAccountId"
    )
    payer_account: str = Field(serialization_alias="payerAccount")
    receiver_account: str = Field(serialization_alias="receiverAccount")
    payer_account_detail: BankAccountOut | None = Field(
        None, serialization_alias="payerAccountDetail"
    )
    receiver_account_detail: BankAccountOut | None = Field(
        None, serialization_alias="receiverAccountDetail"
    )
    payment_date: date | None = Field(None, serialization_alias="paymentDate")
    reason: str | None = None
    installment_count: int | None = Field(None, serialization_alias="installmentCount")
    first_installment_date: date | None = Field(
        None,
        serialization_alias="firstInstallmentDate",
    )
    settlement_date: date | None = Field(None, serialization_alias="settlementDate")
    payment_order_kind: str | None = Field(None, serialization_alias="paymentOrderKind")
    payment_marked_at: datetime | None = Field(None, serialization_alias="paymentMarkedAt")
    payment_marked_by: int | None = Field(None, serialization_alias="paymentMarkedBy")
    status: str
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    workflow_instance_id: int | None = Field(
        None,
        serialization_alias="workflowInstanceId",
        description="پر می‌شود وقتی با workflow-instance resolve شود",
    )
    attachments: list[AttachmentOut] = Field(default_factory=list)
    attachment_count: int = Field(0, serialization_alias="attachmentCount")


class PaymentRequestListResponse(BaseModel):
    items: list[PaymentRequestOut]
    total: int
    page: int
    pageSize: int
