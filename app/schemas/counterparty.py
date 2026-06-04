from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.bank_account import BankAccountOut


class CounterpartyCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255)
    party_type: str = Field(default="company", validation_alias="partyType")
    company_name: str | None = Field(None, max_length=255, validation_alias="companyName")
    account_number: str | None = Field(None, max_length=50, validation_alias="accountNumber")
    sheba_number: str | None = Field(None, max_length=26, validation_alias="shebaNumber")
    card_number: str | None = Field(None, max_length=24, validation_alias="cardNumber")
    notes: str | None = Field(None, max_length=500)
    is_active: bool = Field(True, validation_alias="isActive")

    @field_validator("party_type")
    @classmethod
    def validate_party_type(cls, value: str) -> str:
        v = (value or "company").strip().lower()
        if v not in ("person", "company"):
            raise ValueError("party_type must be person or company")
        return v


class CounterpartyUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(None, min_length=1, max_length=255)
    party_type: str | None = Field(None, pattern="^(person|company)$", validation_alias="partyType")
    company_name: str | None = Field(None, max_length=255, validation_alias="companyName")
    account_number: str | None = Field(None, max_length=50, validation_alias="accountNumber")
    sheba_number: str | None = Field(None, max_length=26, validation_alias="shebaNumber")
    card_number: str | None = Field(None, max_length=24, validation_alias="cardNumber")
    notes: str | None = Field(None, max_length=500)
    is_active: bool | None = Field(None, validation_alias="isActive")


class CounterpartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    party_type: str = Field(serialization_alias="partyType")
    company_name: str | None = Field(None, serialization_alias="companyName")
    account_number: str | None = Field(None, serialization_alias="accountNumber")
    sheba_number: str | None = Field(None, serialization_alias="shebaNumber")
    card_number: str | None = Field(None, serialization_alias="cardNumber")
    notes: str | None = None
    is_active: bool = Field(serialization_alias="isActive")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    updated_at: datetime | None = Field(None, serialization_alias="updatedAt")
    bank_accounts: list[BankAccountOut] = Field(
        default_factory=list,
        serialization_alias="bankAccounts",
    )


class CounterpartyListResponse(BaseModel):
    items: list[CounterpartyOut]
    total: int
    page: int
    pageSize: int
