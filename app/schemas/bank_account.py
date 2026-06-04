from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BankAccountBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str = Field(..., min_length=1, max_length=120)
    bank_name: str | None = Field(None, max_length=120, validation_alias="bankName")
    account_number: str | None = Field(None, max_length=50, validation_alias="accountNumber")
    sheba_number: str | None = Field(None, max_length=26, validation_alias="shebaNumber")
    card_number: str | None = Field(None, max_length=24, validation_alias="cardNumber")
    is_default: bool = Field(False, validation_alias="isDefault")

    @model_validator(mode="after")
    def at_least_one_identifier(self):
        if not any(
            [
                (self.account_number or "").strip(),
                (self.sheba_number or "").strip(),
                (self.card_number or "").strip(),
            ]
        ):
            raise ValueError("حداقل یکی از شماره حساب، شبا یا کارت الزامی است")
        return self


class BankAccountCreate(BankAccountBase):
    is_active: bool = Field(True, validation_alias="isActive")


class BankAccountUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str | None = Field(None, min_length=1, max_length=120)
    bank_name: str | None = Field(None, max_length=120, validation_alias="bankName")
    account_number: str | None = Field(None, max_length=50, validation_alias="accountNumber")
    sheba_number: str | None = Field(None, max_length=26, validation_alias="shebaNumber")
    card_number: str | None = Field(None, max_length=24, validation_alias="cardNumber")
    is_default: bool | None = Field(None, validation_alias="isDefault")
    is_active: bool | None = Field(None, validation_alias="isActive")


class BankAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    label: str
    bank_name: str | None = Field(None, serialization_alias="bankName")
    account_number: str | None = Field(None, serialization_alias="accountNumber")
    sheba_number: str | None = Field(None, serialization_alias="shebaNumber")
    card_number: str | None = Field(None, serialization_alias="cardNumber")
    is_default: bool = Field(False, serialization_alias="isDefault")
    is_active: bool = Field(True, serialization_alias="isActive")
    display_label: str | None = Field(None, serialization_alias="displayLabel")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(None, serialization_alias="updatedAt")
