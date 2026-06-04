from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.schemas.money import MoneyAmount, OptionalMoneyAmount


class WorkflowFormUpdate(BaseModel):
    receiver_id: int | None = None
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class WorkflowFormCreate(BaseModel):
    receiver_id: int
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class LoanAdvanceRequestCreate(BaseModel):
    """درخواست وام یا مساعده — فقط مبلغ، تاریخ و توضیح توسط کارمند."""

    amount: MoneyAmount
    payment_date: date | None = Field(
        None,
        description="تاریخ درخواست (همان paymentDate در API)",
    )
    reason: str | None = Field(default=None, max_length=2000)
    assignees_by_order: dict[str, int] | None = Field(
        default=None,
        description="Optional 1-based step index -> user id for explicit assignees",
    )


class LoanAdvanceRequestUpdate(BaseModel):
    amount: OptionalMoneyAmount = None
    payment_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)


class PaymentRequestUpdate(BaseModel):
    payment_type: str | None = Field(default=None, min_length=2, max_length=50)
    payment_method: str | None = Field(
        default=None,
        validation_alias="paymentMethod",
        description="دستور پرداخت: check یا transfer",
    )
    amount: OptionalMoneyAmount = None
    payer_account: str | None = Field(default=None, min_length=2, max_length=100)
    receiver_account: str | None = Field(default=None, min_length=2, max_length=100)
    payment_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)


class PaymentOrderCreate(BaseModel):
    """دستور پرداخت — انفرادی (با طرف‌حساب) یا جمعی."""

    model_config = {"populate_by_name": True}

    payment_order_kind: str = Field(
        "individual",
        validation_alias="paymentOrderKind",
        description="individual | collective",
    )
    counterparty_id: int | None = Field(None, description="شناسه طرف حساب — انفرادی الزامی")
    payer_company_account_id: int | None = Field(
        None,
        validation_alias="payerCompanyAccountId",
        description="حساب بانکی شرکت (مبدأ پرداخت) — در صورت خالی، در تأیید تعیین می‌شود",
    )
    counterparty_bank_account_id: int | None = Field(
        None,
        validation_alias="counterpartyBankAccountId",
        description="حساب بانکی طرف‌حساب (مقصد) — انفرادی الزامی",
    )
    amount: OptionalMoneyAmount = None
    payment_method: str = Field(
        ...,
        validation_alias="paymentMethod",
        description="check (چک) یا transfer (حواله)",
    )
    payment_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)
    assignees_by_order: dict[str, int] | None = Field(
        default=None,
        description="Optional 1-based step index -> user id for explicit assignees",
    )

    @model_validator(mode="after")
    def validate_order_kind(self) -> "PaymentOrderCreate":
        kind = (self.payment_order_kind or "individual").strip().lower()
        if kind not in ("individual", "collective"):
            raise ValueError("paymentOrderKind باید individual یا collective باشد")
        if kind == "individual":
            if not self.counterparty_id:
                raise ValueError("برای دستور پرداخت انفرادی طرف حساب الزامی است")
            if not self.counterparty_bank_account_id:
                raise ValueError("برای دستور پرداخت انفرادی حساب مقصد الزامی است")
            if self.amount is None or self.amount <= 0:
                raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")
        elif self.amount is None:
            object.__setattr__(self, "amount", 0.0)
        return self


class PaymentRequestCreate(BaseModel):
    model_config = {"populate_by_name": True}

    payment_type: str = Field(min_length=2, max_length=50)
    amount: MoneyAmount
    payer_company_account_id: int | None = Field(
        None,
        validation_alias="payerCompanyAccountId",
    )
    counterparty_bank_account_id: int | None = Field(
        None,
        validation_alias="counterpartyBankAccountId",
    )
    payer_account: str | None = Field(default=None, min_length=2, max_length=100)
    receiver_account: str | None = Field(default=None, min_length=2, max_length=100)
    counterparty_id: int | None = Field(
        default=None,
        description="برای payment_order الزامی است",
    )
    payment_date: date | None = None
    reason: str | None = Field(default=None, max_length=2000)
    assignees_by_order: dict[str, int] | None = Field(
        default=None,
        description="Optional 1-based step index -> user id for explicit assignees",
    )


class WarehouseFormUpdate(BaseModel):
    form_type: str | None = Field(default=None, min_length=2, max_length=20)
    source: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    receiver_name: str | None = Field(default=None, max_length=255)
    effective_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)


class WarehouseFormCreate(BaseModel):
    form_type: str = Field(min_length=2, max_length=20)
    source: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    receiver_name: str | None = Field(default=None, max_length=255)
    effective_date: date | None = None
    description: str | None = Field(default=None, max_length=2000)
    assignees_by_order: dict[str, int] | None = Field(
        default=None,
        description="Optional 1-based step index -> user id for explicit assignees",
    )
