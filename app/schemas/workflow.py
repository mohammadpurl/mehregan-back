from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import OptionalMoneyAmount


class WorkflowRejectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    comment: str = Field(..., min_length=1, max_length=2000)
    return_to: str = Field(
        "requester",
        alias="returnTo",
        description="previous | requester",
    )


class WorkflowApproveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    comment: str | None = None
    amount: OptionalMoneyAmount = None
    payment_date: date | None = Field(
        None,
        validation_alias="paymentDate",
        description="تاریخ پرداخت — قابل تغییر توسط تأییدکننده",
    )
    installment_count: int | None = Field(
        None,
        ge=1,
        description="وام: تعداد اقساط — فقط تأییدکننده",
    )
    first_installment_date: date | None = Field(
        None,
        description="وام: تاریخ شروع قسط اول — فقط تأییدکننده",
    )
    settlement_date: date | None = Field(
        None,
        description="مساعده: تاریخ تسویه — فقط تأییدکننده",
    )
    payer_company_account_id: int | None = Field(
        None,
        validation_alias="payerCompanyAccountId",
        description="حساب بانکی شرکت (مبدأ پرداخت) — انتخاب از لیست تعریف‌شده",
    )
    payer_account: str | None = Field(
        None,
        min_length=2,
        max_length=100,
        description="(قدیمی) فقط اگر payerCompanyAccountId ارسال نشود",
    )
    payment_method: str | None = Field(
        None,
        validation_alias="paymentMethod",
        description="دستور پرداخت: check (چک) یا transfer (حواله)",
    )
    payment_executed: bool = Field(
        False,
        validation_alias="paymentExecuted",
        description="مرحله ثبت پرداخت: پرداخت انجام شد",
    )
