import re

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

_ACCOUNT_NUMBER_RE = re.compile(r"^\d{5,30}$")
_CARD_NUMBER_RE = re.compile(r"^\d{16,19}$")
_SHEBA_RE = re.compile(r"^IR\d{24}$", re.IGNORECASE)


class UserBankingFieldsMixin(BaseModel):
    """شماره حساب، کارت و شبا — اختیاری."""

    model_config = ConfigDict(populate_by_name=True)

    account_number: str | None = Field(
        None,
        max_length=50,
        validation_alias=AliasChoices("accountNumber", "account_number"),
    )
    card_number: str | None = Field(
        None,
        max_length=32,
        validation_alias=AliasChoices("cardNumber", "card_number"),
    )
    sheba_number: str | None = Field(
        None,
        max_length=34,
        description="۲۴ رقم (با یا بدون IR) — پس از اعتبارسنجی به IR+24 رقم ذخیره می‌شود",
        validation_alias=AliasChoices("shebaNumber", "sheba_number"),
    )

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.replace(" ", "").replace("-", "")
        if not value:
            return None
        if not _ACCOUNT_NUMBER_RE.match(value):
            raise ValueError("شماره حساب باید ۵ تا ۳۰ رقم باشد")
        return value

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.replace(" ", "").replace("-", "")
        if not value:
            return None
        if not _CARD_NUMBER_RE.match(value):
            raise ValueError("شماره کارت باید ۱۶ تا ۱۹ رقم باشد")
        return value

    @field_validator("sheba_number")
    @classmethod
    def validate_sheba_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.replace(" ", "").upper()
        if not value:
            return None
        if not value.startswith("IR"):
            value = f"IR{value}"
        if not _SHEBA_RE.match(value):
            raise ValueError("شماره شبا باید به صورت IR و ۲۴ رقم باشد")
        return value
